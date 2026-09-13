import type { AsyncBackend, Message, ToolDefinition } from "../llm/index.js";
import { Role } from "../llm/index.js";
import type { Response } from "../llm/response.js";
import type { ToolRegistry } from "../tools/index.js";
import { executeTool, Result } from "../tools/index.js";
import type {
  ResponseValidator,
  ValidationResult,
} from "../middleware/guardrails/response_validator.js";
import {
  ErrorTracker,
  ErrorCategory,
} from "../middleware/guardrails/error_tracker.js";
import { StepEnforcer } from "../middleware/guardrails/step_enforcer.js";
import {
  Nudge,
  NudgeKind,
  stepNudge,
} from "../middleware/guardrails/nudge.js";
import { MessageType } from "../middleware/types.js";

export enum AgentTerminationReason {
  COMPLETE = "complete",
  MAX_ITERATIONS = "max_iterations",
  NUDGES_EXHAUSTED = "nudges_exhausted",
  ERROR = "error",
}

export interface AgentLoopConfig {
  backend: AsyncBackend;
  registry: ToolRegistry;
  validator: ResponseValidator;
  error_tracker?: ErrorTracker;
  step_enforcer?: StepEnforcer;
  max_iterations?: number;
  max_nudges?: number;
  require_tool_call?: boolean;
}

export interface AgentResult {
  final_response: string;
  iterations: number;
  tool_calls_made: number;
  nudges: number;
  termination_reason: AgentTerminationReason;
  conversation: Message[];
}

export function registryToolDefinitions(
  registry: ToolRegistry
): ToolDefinition[] {
  return registry.all().map((tool) => ({
    name: tool.name,
    description: tool.description,
    input_schema:
      "inputSchema" in tool
        ? (tool as unknown as { inputSchema(): Record<string, unknown> }).inputSchema()
        : {},
  }));
}

export function categorizeError(message: string): ErrorCategory {
  const m = message.toLowerCase();
  if (m.includes("timeout") || m.includes("timed out")) {
    return ErrorCategory.TIMEOUT;
  }
  if (m.includes("not found") || m.includes("unknown tool")) {
    return ErrorCategory.NOT_FOUND;
  }
  if (
    m.includes("invalid arg") ||
    m.includes("schema") ||
    m.includes("validation")
  ) {
    return ErrorCategory.INVALID_ARGS;
  }
  if (
    m.includes("permission") ||
    m.includes("denied") ||
    m.includes("forbidden")
  ) {
    return ErrorCategory.PERMISSION;
  }
  if (m.includes("rate limit") || m.includes("rate_limit")) {
    return ErrorCategory.RATE_LIMIT;
  }
  return ErrorCategory.UNKNOWN;
}

function nudgeMetaType(kind: NudgeKind): MessageType {
  switch (kind) {
    case NudgeKind.STEP:
      return MessageType.STEP_NUDGE;
    case NudgeKind.PREREQUISITE:
      return MessageType.PREREQUISITE_NUDGE;
    default:
      return MessageType.RETRY_NUDGE;
  }
}

function toError(err: unknown): Error {
  return err instanceof Error ? err : new Error(String(err));
}

export class AgentLoop {
  private readonly config: AgentLoopConfig;
  private readonly maxIterations: number;
  private readonly maxNudges: number;

  constructor(config: AgentLoopConfig) {
    this.config = config;
    this.maxIterations =
      config.max_iterations && config.max_iterations > 0
        ? config.max_iterations
        : 20;
    this.maxNudges =
      config.max_nudges && config.max_nudges > 0 ? config.max_nudges : 3;
  }

  async run(
    system_prompt: string,
    user_message: string,
    history: Message[] = [],
    session_id: string = ""
  ): Promise<AgentResult> {
    const conversation: Message[] = [...history];
    conversation.push({ role: Role.SYSTEM, content: system_prompt });
    conversation.push({ role: Role.USER, content: user_message });

    const toolDefs = registryToolDefinitions(this.config.registry);

    let iterations = 0;
    let toolCallsMade = 0;
    let nudges = 0;
    let finalResponse = "";

    while (iterations < this.maxIterations) {
      iterations++;

      let resp: Response;
      try {
        resp = await this.config.backend.complete(conversation, toolDefs);
      } catch (err) {
        this.config.error_tracker?.recordError(
          session_id,
          "",
          {},
          toError(err),
          ErrorCategory.UNKNOWN
        );
        return this.finish(
          finalResponse,
          iterations,
          toolCallsMade,
          nudges,
          AgentTerminationReason.ERROR,
          conversation
        );
      }

      const validation = this.validate(resp);

      if (validation.needsRetry) {
        if (nudges >= this.maxNudges) {
          return this.finish(
            resp.content,
            iterations,
            toolCallsMade,
            nudges,
            AgentTerminationReason.NUDGES_EXHAUSTED,
            conversation
          );
        }
        nudges++;
        conversation.push({
          role: Role.ASSISTANT,
          content: resp.content,
          meta: { type: MessageType.TEXT_RESPONSE },
        });
        if (validation.nudge) {
          conversation.push({
            role: Role.USER,
            content: validation.nudge.content,
            meta: { type: nudgeMetaType(validation.nudge.kind) },
          });
        }
        continue;
      }

      if (validation.toolCalls.length === 0) {
        finalResponse = resp.content;
        return this.finish(
          finalResponse,
          iterations,
          toolCallsMade,
          nudges,
          AgentTerminationReason.COMPLETE,
          conversation
        );
      }

      let stepNudged = false;

      for (const call of validation.toolCalls) {
        if (this.config.step_enforcer) {
          const [allowed, missing] = this.config.step_enforcer.canExecute(
            session_id,
            call.tool
          );
          if (!allowed) {
            if (nudges >= this.maxNudges) {
              return this.finish(
                resp.content,
                iterations,
                toolCallsMade,
                nudges,
                AgentTerminationReason.NUDGES_EXHAUSTED,
                conversation
              );
            }
            nudges++;
            stepNudged = true;
            const nudge: Nudge = stepNudge(
              call.tool,
              missing,
              Math.min(3, nudges)
            );
            conversation.push({
              role: Role.USER,
              content: nudge.content,
              meta: { type: MessageType.STEP_NUDGE },
            });
            continue;
          }
        }

        if (
          this.config.error_tracker &&
          this.config.error_tracker.shouldBlockTool(session_id, call.tool)
        ) {
          conversation.push({
            role: Role.TOOL,
            content: `Tool ${call.tool} error: blocked after repeated errors`,
            meta: { type: MessageType.TOOL_RESULT },
          });
          continue;
        }

        const tool = this.config.registry.get(call.tool);
        if (!tool) {
          conversation.push({
            role: Role.TOOL,
            content: `Tool ${call.tool} error: unknown tool`,
            meta: { type: MessageType.TOOL_RESULT },
          });
          continue;
        }

        toolCallsMade++;

        let result: Result;
        try {
          result = await executeTool(tool, call.args);
        } catch (err) {
          result = new Result(false, null, toError(err).message);
        }

        if (result.success) {
          this.config.step_enforcer?.markStepComplete(session_id, call.tool);
          conversation.push({
            role: Role.TOOL,
            content: `Tool ${call.tool} result: ${JSON.stringify(result.data)}`,
            meta: { type: MessageType.TOOL_RESULT },
          });
        } else {
          const message = result.error ?? "tool failed";
          this.config.error_tracker?.recordError(
            session_id,
            call.tool,
            call.args,
            new Error(message),
            categorizeError(message)
          );
          conversation.push({
            role: Role.TOOL,
            content: `Tool ${call.tool} error: ${message}`,
            meta: { type: MessageType.TOOL_RESULT },
          });
        }
      }

      if (stepNudged) {
        continue;
      }
    }

    return this.finish(
      finalResponse,
      iterations,
      toolCallsMade,
      nudges,
      AgentTerminationReason.MAX_ITERATIONS,
      conversation
    );
  }

  private validate(resp: Response): ValidationResult {
    if (resp.tool_calls.length > 0) {
      return this.config.validator.validateToolCalls(
        resp.tool_calls.map((tc) => ({ tool: tc.name, args: tc.arguments }))
      );
    }
    const textValidation =
      this.config.validator.validateTextResponse(resp.content);
    if (textValidation.toolCalls.length > 0) {
      return textValidation;
    }
    if (this.config.require_tool_call) {
      return textValidation;
    }
    return { toolCalls: [], nudge: null, needsRetry: false };
  }

  private finish(
    finalResponse: string,
    iterations: number,
    toolCallsMade: number,
    nudges: number,
    termination: AgentTerminationReason,
    conversation: Message[]
  ): AgentResult {
    return {
      final_response: finalResponse,
      iterations,
      tool_calls_made: toolCallsMade,
      nudges,
      termination_reason: termination,
      conversation,
    };
  }
}
