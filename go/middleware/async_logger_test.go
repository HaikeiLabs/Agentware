package middleware

import (
	"sync"
	"testing"
	"time"
)

// recordingSink is a thread-safe Auditor used as the downstream target of an
// AsyncLogger under test.
type recordingSink struct {
	mu       sync.Mutex
	records  []AuditRecord
	batches  int
	onRecord func()
	delay    time.Duration
}

func (s *recordingSink) Record(record AuditRecord) {
	if s.delay > 0 {
		time.Sleep(s.delay)
	}
	s.mu.Lock()
	s.records = append(s.records, record)
	s.mu.Unlock()
	if s.onRecord != nil {
		s.onRecord()
	}
}

func (s *recordingSink) Query(filter AuditFilter) []AuditRecord {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]AuditRecord, len(s.records))
	copy(out, s.records)
	return out
}

func (s *recordingSink) count() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.records)
}

func (s *recordingSink) names() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]string, len(s.records))
	for i, r := range s.records {
		out[i] = r.ToolName
	}
	return out
}

// batchingSink additionally implements BatchAuditor.
type batchingSink struct {
	recordingSink
}

func (s *batchingSink) RecordBatch(records []AuditRecord) {
	s.mu.Lock()
	s.records = append(s.records, records...)
	s.batches++
	s.mu.Unlock()
}

func (s *batchingSink) batchCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.batches
}

func TestAsyncLoggerFlushDeliversAllRecords(t *testing.T) {
	sink := &recordingSink{}
	logger := NewAsyncLogger(sink, AsyncLoggerConfig{})
	logger.Start()
	defer logger.Stop()

	for i := 0; i < 10; i++ {
		logger.Log(AuditRecord{ToolName: "tool"})
	}
	logger.Flush()

	if got := sink.count(); got != 10 {
		t.Fatalf("expected 10 records after Flush, got %d", got)
	}
	if got := logger.Dropped(); got != 0 {
		t.Fatalf("expected 0 drops, got %d", got)
	}
}

func TestAsyncLoggerLogIsNonBlocking(t *testing.T) {
	// A sink that blocks on every write must not stall the caller. With a
	// buffer of 1 and a wedged sink, Log still has to return promptly.
	release := make(chan struct{})
	sink := &recordingSink{onRecord: func() { <-release }}
	logger := NewAsyncLogger(sink, AsyncLoggerConfig{
		BufferSize:    1,
		BatchSize:     1,
		FlushInterval: time.Millisecond,
	})
	logger.Start()

	done := make(chan struct{})
	go func() {
		defer close(done)
		for i := 0; i < 100; i++ {
			logger.Log(AuditRecord{ToolName: "tool"})
		}
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		close(release)
		t.Fatal("Log blocked while the sink was wedged")
	}

	close(release)
	logger.Stop()

	// The wedged sink means most records were dropped rather than buffered;
	// what matters is that the drops were counted, not silently lost.
	if sink.count()+logger.Dropped() < 100 {
		t.Fatalf("records unaccounted for: written=%d dropped=%d, want >= 100 total",
			sink.count(), logger.Dropped())
	}
}

func TestAsyncLoggerDropsWhenBufferFull(t *testing.T) {
	var dropped []AuditRecord
	var mu sync.Mutex
	sink := &recordingSink{}
	logger := NewAsyncLogger(sink, AsyncLoggerConfig{
		BufferSize: 2,
		BatchSize:  100, // never auto-writes, so the buffer stays full
		OnDrop: func(r AuditRecord) {
			mu.Lock()
			dropped = append(dropped, r)
			mu.Unlock()
		},
	})
	// Deliberately not started: nothing drains the buffer.

	for i := 0; i < 5; i++ {
		logger.Log(AuditRecord{ToolName: "tool"})
	}

	if got := logger.Dropped(); got != 3 {
		t.Fatalf("expected 3 drops with a buffer of 2 and 5 logs, got %d", got)
	}
	mu.Lock()
	n := len(dropped)
	mu.Unlock()
	if n != 3 {
		t.Fatalf("expected OnDrop to fire 3 times, got %d", n)
	}
}

func TestAsyncLoggerFlushWithoutStartDrainsSynchronously(t *testing.T) {
	sink := &recordingSink{}
	logger := NewAsyncLogger(sink, AsyncLoggerConfig{BufferSize: 8})

	logger.Log(AuditRecord{ToolName: "a"})
	logger.Log(AuditRecord{ToolName: "b"})
	logger.Flush()

	if got := sink.count(); got != 2 {
		t.Fatalf("expected Flush to drain synchronously when not started, got %d records", got)
	}
}

func TestAsyncLoggerStopDrainsRemaining(t *testing.T) {
	sink := &recordingSink{}
	logger := NewAsyncLogger(sink, AsyncLoggerConfig{
		BatchSize:     1000,
		FlushInterval: time.Hour, // only Stop can cause a write
	})
	logger.Start()

	for i := 0; i < 25; i++ {
		logger.Log(AuditRecord{ToolName: "tool"})
	}
	logger.Stop()

	if got := sink.count(); got != 25 {
		t.Fatalf("expected Stop to drain all 25 records, got %d", got)
	}
}

func TestAsyncLoggerLogAfterStopIsDropped(t *testing.T) {
	sink := &recordingSink{}
	logger := NewAsyncLogger(sink, AsyncLoggerConfig{})
	logger.Start()
	logger.Stop()

	logger.Log(AuditRecord{ToolName: "late"})

	if got := sink.count(); got != 0 {
		t.Fatalf("expected no records after Stop, got %d", got)
	}
	if got := logger.Dropped(); got != 1 {
		t.Fatalf("expected the post-Stop record to be counted as dropped, got %d", got)
	}
}

func TestAsyncLoggerStopIsIdempotent(t *testing.T) {
	logger := NewAsyncLogger(&recordingSink{}, AsyncLoggerConfig{})
	logger.Start()
	logger.Stop()
	logger.Stop() // must not panic on a double close
}

func TestAsyncLoggerStartIsIdempotent(t *testing.T) {
	sink := &recordingSink{}
	logger := NewAsyncLogger(sink, AsyncLoggerConfig{})
	logger.Start()
	logger.Start() // a second drain goroutine would double-consume the buffer

	logger.Log(AuditRecord{ToolName: "a"})
	logger.Flush()
	logger.Stop()

	if got := sink.count(); got != 1 {
		t.Fatalf("expected exactly 1 record, got %d", got)
	}
}

func TestAsyncLoggerFlushIntervalShipsPartialBatch(t *testing.T) {
	sink := &recordingSink{}
	logger := NewAsyncLogger(sink, AsyncLoggerConfig{
		BatchSize:     1000, // far above what we log
		FlushInterval: 10 * time.Millisecond,
	})
	logger.Start()
	defer logger.Stop()

	logger.Log(AuditRecord{ToolName: "a"})

	deadline := time.After(2 * time.Second)
	for sink.count() == 0 {
		select {
		case <-deadline:
			t.Fatal("partial batch was never shipped by the flush interval")
		default:
			time.Sleep(time.Millisecond)
		}
	}
}

func TestAsyncLoggerUsesBatchAuditor(t *testing.T) {
	sink := &batchingSink{}
	logger := NewAsyncLogger(sink, AsyncLoggerConfig{
		BatchSize:     1000,
		FlushInterval: time.Hour,
	})
	logger.Start()

	for i := 0; i < 20; i++ {
		logger.Log(AuditRecord{ToolName: "tool"})
	}
	logger.Stop()

	if got := sink.count(); got != 20 {
		t.Fatalf("expected 20 records, got %d", got)
	}
	if got := sink.batchCount(); got != 1 {
		t.Fatalf("expected 20 records to ship as 1 batch, got %d batches", got)
	}
}

func TestAsyncLoggerQueryDelegatesToSink(t *testing.T) {
	sink := &recordingSink{}
	logger := NewAsyncLogger(sink, AsyncLoggerConfig{})
	logger.Start()
	defer logger.Stop()

	logger.Log(AuditRecord{ToolName: "queried"})
	logger.Flush()

	got := logger.Query(AuditFilter{})
	if len(got) != 1 || got[0].ToolName != "queried" {
		t.Fatalf("expected Query to delegate to the sink, got %+v", got)
	}
}

func TestAsyncLoggerNilSinkIsSafe(t *testing.T) {
	logger := NewAsyncLogger(nil, AsyncLoggerConfig{})
	logger.Start()
	logger.Log(AuditRecord{ToolName: "a"})
	logger.Flush()
	logger.Stop()

	if got := logger.Query(AuditFilter{}); got != nil {
		t.Fatalf("expected nil Query result with a nil sink, got %+v", got)
	}
}

func TestAsyncLoggerConcurrentLogAndFlush(t *testing.T) {
	sink := &recordingSink{}
	logger := NewAsyncLogger(sink, AsyncLoggerConfig{BufferSize: 4096})
	logger.Start()

	var wg sync.WaitGroup
	for w := 0; w < 8; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < 100; i++ {
				logger.Log(AuditRecord{ToolName: "tool"})
			}
		}()
	}
	for f := 0; f < 4; f++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < 10; i++ {
				logger.Flush()
			}
		}()
	}
	wg.Wait()
	logger.Stop()

	if got := sink.count() + logger.Dropped(); got != 800 {
		t.Fatalf("expected 800 records written or dropped, got %d (written=%d dropped=%d)",
			got, sink.count(), logger.Dropped())
	}
}

// TestAsyncLoggerAsMiddlewareAuditor exercises the seam the middleware uses:
// an AsyncLogger stands in for the Auditor so tool execution never waits on the
// audit sink.
func TestAsyncLoggerAsMiddlewareAuditor(t *testing.T) {
	sink := &recordingSink{delay: 5 * time.Millisecond}
	logger := NewAsyncLogger(sink, AsyncLoggerConfig{})
	logger.Start()

	m := NewMiddleware(&mockExecutor{}).WithAuditor(logger)

	start := time.Now()
	for i := 0; i < 20; i++ {
		if _, err := m.Execute(t.Context(), "search", map[string]any{"q": "x"}); err != nil {
			t.Fatalf("Execute returned error: %v", err)
		}
	}
	elapsed := time.Since(start)

	// 20 synchronous writes would cost at least 100ms; async must beat that by
	// a wide margin.
	if elapsed > 50*time.Millisecond {
		t.Fatalf("execution blocked on the audit sink: took %v for 20 calls", elapsed)
	}

	logger.Flush()
	if got := sink.count(); got != 20 {
		t.Fatalf("expected 20 audit records after Flush, got %d", got)
	}
	for _, name := range sink.names() {
		if name != "search" {
			t.Fatalf("unexpected tool name in audit record: %q", name)
		}
	}
	logger.Stop()
}
