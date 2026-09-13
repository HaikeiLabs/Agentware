/** A sync or async tool handler with host-supplied context and cancellation. */
export type AsyncToolHandler<Input, Output, Context> = (
  input: Input,
  context: Context,
  signal: AbortSignal,
) => Output | Promise<Output>;

/** A wrapped tool handler. Kept separate so host frameworks can preserve schemas. */
export type WrappedTool<Input, Output, Context> = (
  input: Input,
  context: Context,
  options?: ToolInvocationOptions,
) => Promise<Output>;

/** Per-call cancellation and deadline controls. */
export interface ToolInvocationOptions {
  readonly signal?: AbortSignal;
  readonly timeoutMs?: number;
}

/** Safe lifecycle metadata; it intentionally excludes tool inputs and context. */
export interface ToolLifecycleEvent {
  readonly type: "started" | "succeeded" | "failed" | "aborted" | "timed_out";
  readonly toolName?: string;
  readonly durationMs: number;
}

/** Best-effort event hook for metrics and tracing. Hook failures never affect a tool call. */
export type ToolLifecycleHook = (event: ToolLifecycleEvent) => void;

/** Options fixed when a handler is wrapped. */
export interface WrapToolOptions {
  /** An optional safe identifier included in lifecycle events. */
  readonly name?: string;
  /** Default per-call deadline. A caller may override it through invocation options. */
  readonly timeoutMs?: number;
  /** Receives bounded lifecycle metadata, never raw inputs or context. */
  readonly onEvent?: ToolLifecycleHook;
}

/** Raised when Agentware reaches an invocation deadline. */
export class ToolTimeoutError extends Error {
  readonly timeoutMs: number;

  constructor(timeoutMs: number) {
    super(`Tool execution timed out after ${timeoutMs}ms`);
    this.name = "ToolTimeoutError";
    this.timeoutMs = timeoutMs;
  }
}

/** Raised when the host cancels an invocation. */
export class ToolAbortedError extends Error {
  constructor() {
    super("Tool execution was aborted");
    this.name = "ToolAbortedError";
  }
}

function validateTimeout(timeoutMs: number | undefined): void {
  if (timeoutMs === undefined) return;
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new RangeError("timeoutMs must be a finite positive number");
  }
}

function emit(
  hook: ToolLifecycleHook | undefined,
  type: ToolLifecycleEvent["type"],
  toolName: string | undefined,
  startedAt: number,
): void {
  if (hook === undefined) return;
  try {
    hook({ type, ...(toolName === undefined ? {} : { toolName }), durationMs: Date.now() - startedAt });
  } catch {
    // Observability must not change the tool's execution result.
  }
}

/**
 * Wrap an existing tool without coupling it to a model framework, transport, or
 * policy engine. The wrapper propagates host cancellation and an optional
 * deadline through the handler's AbortSignal.
 */
export function wrapTool<Input, Output, Context>(
  handler: AsyncToolHandler<Input, Output, Context>,
  options: WrapToolOptions = {},
): WrappedTool<Input, Output, Context> {
  validateTimeout(options.timeoutMs);

  return async (input, context, invocation = {}): Promise<Output> => {
    validateTimeout(invocation.timeoutMs);
    const timeoutMs = invocation.timeoutMs ?? options.timeoutMs;
    const startedAt = Date.now();
    const controller = new AbortController();
    const externalSignal = invocation.signal;

    if (externalSignal?.aborted === true) {
      emit(options.onEvent, "aborted", options.name, startedAt);
      throw new ToolAbortedError();
    }

    let timer: ReturnType<typeof setTimeout> | undefined;
    let rejectInterrupted: ((error: Error) => void) | undefined;
    const interrupted = new Promise<never>((_, reject) => {
      rejectInterrupted = reject;
    });

    const abort = (): void => {
      controller.abort();
      rejectInterrupted?.(new ToolAbortedError());
    };
    externalSignal?.addEventListener("abort", abort, { once: true });

    if (timeoutMs !== undefined) {
      timer = setTimeout(() => {
        controller.abort();
        rejectInterrupted?.(new ToolTimeoutError(timeoutMs));
      }, timeoutMs);
    }

    emit(options.onEvent, "started", options.name, startedAt);
    const execution = Promise.resolve().then(() => handler(input, context, controller.signal));

    try {
      const result = await Promise.race([execution, interrupted]);
      emit(options.onEvent, "succeeded", options.name, startedAt);
      return result;
    } catch (error) {
      const type = error instanceof ToolTimeoutError
        ? "timed_out"
        : error instanceof ToolAbortedError
          ? "aborted"
          : "failed";
      emit(options.onEvent, type, options.name, startedAt);
      throw error;
    } finally {
      if (timer !== undefined) clearTimeout(timer);
      externalSignal?.removeEventListener("abort", abort);
    }
  };
}
