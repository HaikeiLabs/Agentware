import {
  AnyTool,
  AsyncTool,
  BaseTool,
  Result,
  ToolRegistry,
  executeTool,
} from "../src/tools/index.js";

class AddTool extends BaseTool {
  constructor() {
    super("add", "Add two numbers");
  }

  execute(args: Record<string, unknown>): Result {
    const a = (args.a as number) || 0;
    const b = (args.b as number) || 0;
    return new Result(true, a + b);
  }
}

class SlowEchoTool implements AsyncTool {
  readonly name = "slow_echo";
  readonly description = "Echo input after a tick";

  async execute(args: Record<string, unknown>): Promise<Result> {
    await new Promise((resolve) => setTimeout(resolve, 5));
    return new Result(true, { echoed: args.value ?? null });
  }
}

class ExplodingTool implements AsyncTool {
  readonly name = "explode";
  readonly description = "Always rejects";

  async execute(_args: Record<string, unknown>): Promise<Result> {
    throw new Error("boom");
  }
}

describe("async tool contracts", () => {
  it("registers sync and async tools in one registry", () => {
    const registry = new ToolRegistry();
    registry.register(new AddTool());
    registry.register(new SlowEchoTool());

    expect(registry.names()).toEqual(["add", "slow_echo"]);
    expect(registry.all()).toHaveLength(2);
    expect(registry.get("add")?.name).toBe("add");
    expect(registry.get("slow_echo")?.name).toBe("slow_echo");
  });

  it("executeTool resolves sync tools", async () => {
    const result = await executeTool(new AddTool(), { a: 2, b: 3 });
    expect(result.success).toBe(true);
    expect(result.data).toBe(5);
  });

  it("executeTool awaits async tools", async () => {
    const result = await executeTool(new SlowEchoTool(), { value: "hi" });
    expect(result.success).toBe(true);
    expect(result.data).toEqual({ echoed: "hi" });
  });

  it("executeTool propagates async tool rejections", async () => {
    await expect(executeTool(new ExplodingTool(), {})).rejects.toThrow("boom");
  });

  it("keeps sync Tool assignable to AnyTool (backward compatible)", () => {
    const tool: AnyTool = new AddTool();
    expect(tool.name).toBe("add");
  });

  it("registry.schemas still works for mixed registries", () => {
    const registry = new ToolRegistry();
    registry.register(new AddTool());
    registry.register(new SlowEchoTool());
    const schemas = registry.schemas();
    expect(Object.keys(schemas)).toEqual([]);
  });
});
