export interface ToolCall {
  id: string;
  name: string;
  arguments: string;
}

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface ModelResult {
  content: string;
  tool_calls: ToolCall[];
  finish_reason: string;
  usage: Usage;
}

export interface ChatMessage {
  role: string;
  content?: string;
}

export interface ToolDefinition {
  type: string;
  function: ToolFunc;
}

export interface ToolFunc {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export class ModelClient {
  private baseURL: string;
  private model: string;
  private apiKey: string;
  private timeout: number;

  constructor(baseURL: string, model: string, apiKey: string = "", timeout: number = 60000) {
    this.baseURL = baseURL;
    this.model = model;
    this.apiKey = apiKey;
    this.timeout = timeout;
  }

  async complete(
    messages: ChatMessage[],
    tools?: ToolDefinition[],
    temperature: number = 0.0,
    maxTokens: number = 2048
  ): Promise<ModelResult> {
    const payload: Record<string, unknown> = {
      model: this.model,
      messages: messages,
      temperature: temperature,
      max_tokens: maxTokens,
    };

    if (tools) {
      payload.tools = tools;
    }

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    if (this.apiKey) {
      headers["Authorization"] = `Bearer ${this.apiKey}`;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(`${this.baseURL}/chat/completions`, {
        method: "POST",
        headers: headers,
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      const data = await response.json() as {
        choices: Array<{
          message: {
            content?: string;
            tool_calls?: Array<{
              id: string;
              function: { name: string; arguments: string };
            }>;
          };
        }>;
        usage: Usage;
      };

      const choice = data.choices[0];
      const toolCalls: ToolCall[] = [];

      if (choice.message.tool_calls) {
        for (const tc of choice.message.tool_calls) {
          toolCalls.push({
            id: tc.id,
            name: tc.function.name,
            arguments: tc.function.arguments,
          });
        }
      }

      return {
        content: choice.message.content || "",
        tool_calls: toolCalls,
        finish_reason: "",
        usage: data.usage,
      };
    } catch (error) {
      clearTimeout(timeoutId);
      if (error instanceof Error && error.name === "AbortError") {
        throw new Error(`Request timeout after ${this.timeout}ms`);
      }
      throw error;
    }
  }
}