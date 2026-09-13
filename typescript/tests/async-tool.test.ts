import {
  ToolAbortedError,
  ToolTimeoutError,
  wrapTool,
} from "../src/tools/index.js";

describe("wrapTool", () => {
  it("preserves typed input, result, and trusted host context for an async tool", async () => {
    const tool = wrapTool(
      async (
        input: { readonly queryId: string },
        context: { readonly principalId: string; readonly verifiedOboGrant: string },
      ) => `${context.principalId}:${input.queryId}`,
      { name: "semantic-model-query" },
    );

    await expect(tool(
      { queryId: "commission-summary" },
      { principalId: "user-123", verifiedOboGrant: "host-supplied-only" },
    )).resolves.toBe("user-123:commission-summary");
  });

  it("also supports a synchronous handler", async () => {
    const tool = wrapTool((input: number) => input * 2);

    await expect(tool(21, undefined)).resolves.toBe(42);
  });

  it("passes cancellation to the handler and rejects a cancelled call", async () => {
    const controller = new AbortController();
    const tool = wrapTool(async (_input: undefined, _context: undefined, signal) => {
      await new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve(), { once: true }));
      expect(signal.aborted).toBe(true);
      return "unreachable";
    });

    const result = tool(undefined, undefined, { signal: controller.signal });
    controller.abort();

    await expect(result).rejects.toBeInstanceOf(ToolAbortedError);
  });

  it("aborts a handler at its deadline", async () => {
    const tool = wrapTool(async (_input: undefined, _context: undefined, signal) => {
      await new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve(), { once: true }));
      expect(signal.aborted).toBe(true);
      return "unreachable";
    }, { timeoutMs: 10 });

    await expect(tool(undefined, undefined)).rejects.toEqual(expect.objectContaining({
      name: "ToolTimeoutError",
      timeoutMs: 10,
    }));
  });

  it("does not invoke a handler when the host signal is already aborted", async () => {
    const controller = new AbortController();
    controller.abort();
    let calls = 0;
    const handler = async (): Promise<string> => {
      calls += 1;
      return "should-not-run";
    };
    const tool = wrapTool(handler);

    await expect(tool(undefined, undefined, { signal: controller.signal })).rejects.toBeInstanceOf(ToolAbortedError);
    expect(calls).toBe(0);
  });

  it("emits bounded lifecycle events and ignores hook failures", async () => {
    const events: string[] = [];
    const tool = wrapTool(async () => "done", {
      name: "safe-tool-name",
      onEvent: (event) => {
        events.push(event.type);
        expect(event).not.toHaveProperty("input");
        expect(event).not.toHaveProperty("context");
        if (event.type === "started") throw new Error("metrics unavailable");
      },
    });

    await expect(tool({ secret: "not-emitted" }, { tenant: "not-emitted" })).resolves.toBe("done");
    expect(events).toEqual(["started", "succeeded"]);
  });

  it("rejects invalid deadlines before invoking the handler", async () => {
    expect(() => wrapTool(async () => "never", { timeoutMs: 0 })).toThrow(RangeError);

    let calls = 0;
    const handler = async (): Promise<string> => {
      calls += 1;
      return "never";
    };
    const tool = wrapTool(handler);
    await expect(tool(undefined, undefined, { timeoutMs: Number.NaN })).rejects.toThrow(RangeError);
    expect(calls).toBe(0);
  });
});
