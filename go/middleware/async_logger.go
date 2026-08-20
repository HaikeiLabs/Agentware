package middleware

import (
	"sync"
	"time"
)

// DefaultAsyncBufferSize is the buffer depth used when AsyncLoggerConfig omits
// one. It is sized to absorb a burst of tool calls without blocking the caller
// while keeping the worst-case loss on a hard crash bounded.
const DefaultAsyncBufferSize = 1024

// DefaultFlushInterval is how often the drain goroutine ships a partial batch
// that has not yet reached BatchSize.
const DefaultFlushInterval = time.Second

// DefaultBatchSize is the number of records the drain goroutine accumulates
// before writing them downstream in one call.
const DefaultBatchSize = 64

// AsyncLoggerConfig tunes the buffering behaviour of an AsyncLogger.
type AsyncLoggerConfig struct {
	// BufferSize is the depth of the in-memory channel. Defaults to
	// DefaultAsyncBufferSize.
	BufferSize int
	// BatchSize is how many records accumulate before a downstream write.
	// Defaults to DefaultBatchSize.
	BatchSize int
	// FlushInterval bounds how long a record waits in a partial batch.
	// Defaults to DefaultFlushInterval.
	FlushInterval time.Duration
	// OnDrop is invoked for every record discarded because the buffer was
	// full. It runs on the caller's goroutine, so it must not block.
	OnDrop func(record AuditRecord)
}

// AsyncLogger decouples audit recording from the audit sink. Log enqueues onto
// an in-memory buffer and returns immediately; a background goroutine batches
// records and writes them to the downstream Auditor, so a slow or unreachable
// sink never adds latency to tool execution.
//
// The buffer is bounded. When it is full, Log drops the record rather than
// blocking the caller — availability of the agent is preferred over
// completeness of the audit trail, and drops are counted and reported through
// Dropped and the OnDrop callback.
//
// An AsyncLogger is an Auditor, so it composes with the existing middleware
// seam: NewMiddleware(exec).WithAuditor(NewAsyncLogger(remote, cfg)).
type AsyncLogger struct {
	sink   Auditor
	cfg    AsyncLoggerConfig
	buffer chan AuditRecord

	// done is closed by the drain goroutine once it has exited and the final
	// batch has been written.
	done chan struct{}
	// flushReq carries synchronous flush requests to the drain goroutine. The
	// goroutine closes the delivered channel once every record enqueued before
	// the request has been written downstream.
	flushReq chan chan struct{}

	mu      sync.Mutex
	started bool
	stopped bool

	droppedMu sync.Mutex
	dropped   int
}

// NewAsyncLogger returns an AsyncLogger that writes to sink. Zero-valued config
// fields fall back to the package defaults. The logger does not accept records
// until Start is called.
func NewAsyncLogger(sink Auditor, cfg AsyncLoggerConfig) *AsyncLogger {
	if cfg.BufferSize <= 0 {
		cfg.BufferSize = DefaultAsyncBufferSize
	}
	if cfg.BatchSize <= 0 {
		cfg.BatchSize = DefaultBatchSize
	}
	if cfg.FlushInterval <= 0 {
		cfg.FlushInterval = DefaultFlushInterval
	}
	return &AsyncLogger{
		sink:     sink,
		cfg:      cfg,
		buffer:   make(chan AuditRecord, cfg.BufferSize),
		done:     make(chan struct{}),
		flushReq: make(chan chan struct{}),
	}
}

// Start launches the background drain goroutine. It is safe to call more than
// once; subsequent calls are no-ops.
func (l *AsyncLogger) Start() {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.started || l.stopped {
		return
	}
	l.started = true
	go l.drain()
}

// Log enqueues record for background delivery. It never blocks: if the buffer
// is full the record is dropped, the drop counter is incremented, and OnDrop is
// invoked. Log satisfies the Auditor interface.
func (l *AsyncLogger) Log(record AuditRecord) {
	l.mu.Lock()
	stopped := l.stopped
	l.mu.Unlock()
	if stopped {
		l.recordDrop(record)
		return
	}

	select {
	case l.buffer <- record:
	default:
		l.recordDrop(record)
	}
}

// Record makes AsyncLogger an Auditor. It is an alias for Log.
func (l *AsyncLogger) Record(record AuditRecord) {
	l.Log(record)
}

// Query delegates to the downstream sink so an AsyncLogger can stand in for it
// wherever an Auditor is expected. Records still sitting in the buffer are not
// visible; call Flush first if the caller needs read-after-write consistency.
func (l *AsyncLogger) Query(filter AuditFilter) []AuditRecord {
	if l.sink == nil {
		return nil
	}
	return l.sink.Query(filter)
}

// Flush blocks until every record enqueued before the call has been written to
// the downstream sink. If the drain goroutine is not running, Flush drains the
// buffer synchronously on the caller's goroutine so that callers who never
// started the logger still get their records through.
func (l *AsyncLogger) Flush() {
	l.mu.Lock()
	running := l.started && !l.stopped
	l.mu.Unlock()

	if !running {
		l.drainBufferedSync()
		return
	}

	ack := make(chan struct{})
	select {
	case l.flushReq <- ack:
		<-ack
	case <-l.done:
		// The drain goroutine exited while we were waiting; it wrote
		// everything it held, so sweep anything enqueued since.
		l.drainBufferedSync()
	}
}

// Stop flushes any buffered records, shuts the drain goroutine down, and blocks
// until it has exited. After Stop, Log drops every record. It is safe to call
// more than once.
func (l *AsyncLogger) Stop() {
	l.mu.Lock()
	if l.stopped {
		l.mu.Unlock()
		return
	}
	wasStarted := l.started
	l.stopped = true
	l.mu.Unlock()

	close(l.buffer)
	if wasStarted {
		<-l.done
		return
	}
	// Never started: nobody will drain the buffer, so do it here.
	l.drainBufferedSync()
	close(l.done)
}

// Dropped returns the number of records discarded because the buffer was full.
func (l *AsyncLogger) Dropped() int {
	l.droppedMu.Lock()
	defer l.droppedMu.Unlock()
	return l.dropped
}

func (l *AsyncLogger) recordDrop(record AuditRecord) {
	l.droppedMu.Lock()
	l.dropped++
	l.droppedMu.Unlock()
	if l.cfg.OnDrop != nil {
		l.cfg.OnDrop(record)
	}
}

// drain is the background goroutine started by Start. It batches records and
// writes them downstream, shipping a partial batch every FlushInterval so that
// a low-traffic agent still gets its audit trail out in bounded time.
func (l *AsyncLogger) drain() {
	defer close(l.done)

	ticker := time.NewTicker(l.cfg.FlushInterval)
	defer ticker.Stop()

	batch := make([]AuditRecord, 0, l.cfg.BatchSize)
	write := func() {
		if len(batch) == 0 {
			return
		}
		l.writeBatch(batch)
		batch = batch[:0]
	}

	for {
		select {
		case record, ok := <-l.buffer:
			if !ok {
				// Stop closed the buffer. Writing the batch we hold is not
				// enough: records may have been enqueued after our last read,
				// so drain what remains before exiting.
				write()
				for r := range l.buffer {
					batch = append(batch, r)
					if len(batch) >= l.cfg.BatchSize {
						write()
					}
				}
				write()
				return
			}
			batch = append(batch, record)
			if len(batch) >= l.cfg.BatchSize {
				write()
			}
		case ack := <-l.flushReq:
			// Everything enqueued before the request is already in the buffer,
			// so sweep it into the batch before acknowledging.
			for {
				select {
				case r, ok := <-l.buffer:
					if !ok {
						write()
						close(ack)
						return
					}
					batch = append(batch, r)
					continue
				default:
				}
				break
			}
			write()
			close(ack)
		case <-ticker.C:
			write()
		}
	}
}

// drainBufferedSync writes whatever is currently buffered on the calling
// goroutine. It is used when no drain goroutine is running.
func (l *AsyncLogger) drainBufferedSync() {
	batch := make([]AuditRecord, 0, l.cfg.BatchSize)
	for {
		select {
		case r, ok := <-l.buffer:
			if !ok {
				l.writeBatch(batch)
				return
			}
			batch = append(batch, r)
			continue
		default:
		}
		break
	}
	l.writeBatch(batch)
}

// writeBatch ships records to the downstream sink. The Auditor interface is
// record-at-a-time, so a batching sink is detected through BatchAuditor.
func (l *AsyncLogger) writeBatch(batch []AuditRecord) {
	if l.sink == nil || len(batch) == 0 {
		return
	}
	if b, ok := l.sink.(BatchAuditor); ok {
		b.RecordBatch(batch)
		return
	}
	for _, r := range batch {
		l.sink.Record(r)
	}
}

// BatchAuditor is an optional interface an Auditor may implement to accept a
// whole batch in one call. A remote sink should implement it so a batch costs
// one round trip instead of one per record. The slice is reused after the call
// returns, so implementations must not retain it.
type BatchAuditor interface {
	RecordBatch(records []AuditRecord)
}
