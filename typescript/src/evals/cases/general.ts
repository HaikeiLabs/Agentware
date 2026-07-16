import { EvalCase, ToolDefinition } from "../runner.js";

export const GeneralTools: ToolDefinition[] = [
  {
    type: "function",
    function: {
      name: "calculator",
      description: "Perform mathematical calculations",
      parameters: {
        type: "object",
        properties: {
          expression: {
            type: "string",
            description: "Mathematical expression to evaluate",
          },
        },
        required: ["expression"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_weather",
      description: "Get weather information for a location",
      parameters: {
        type: "object",
        properties: {
          location: {
            type: "string",
            description: "City name",
          },
          units: {
            type: "string",
            enum: ["celsius", "fahrenheit"],
            description: "Temperature units",
          },
        },
        required: ["location"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "translate",
      description: "Translate text between languages",
      parameters: {
        type: "object",
        properties: {
          text: {
            type: "string",
            description: "Text to translate",
          },
          target_lang: {
            type: "string",
            description: "Target language code",
          },
          source_lang: {
            type: "string",
            description: "Source language code (optional, auto-detect if not provided)",
          },
        },
        required: ["text", "target_lang"],
      },
    },
  },
];

export const GeneralCases: EvalCase[] = [
  {
    name: "calculator_add",
    description: "Simple addition calculation",
    systemPrompt: "You are a helpful assistant with access to tools. Use them when needed.",
    userMessage: "What is 123 + 456?",
    tools: GeneralTools,
    expectedTool: "calculator",
    maxTurns: 10,
  },
  {
    name: "calculator_complex",
    description: "Complex mathematical expression",
    systemPrompt: "You are a helpful assistant with access to tools. Use them when needed.",
    userMessage: "Calculate (15 * 8) + (100 / 4) - 50",
    tools: GeneralTools,
    expectedTool: "calculator",
    maxTurns: 10,
  },
  {
    name: "get_weather",
    description: "Get weather for a city",
    systemPrompt: "You are a helpful assistant with access to tools. Use them when needed.",
    userMessage: "What's the weather like in Tokyo?",
    tools: GeneralTools,
    expectedTool: "get_weather",
    maxTurns: 10,
  },
  {
    name: "translate_english_to_spanish",
    description: "Translate text to Spanish",
    systemPrompt: "You are a helpful assistant with access to tools. Use them when needed.",
    userMessage: "Translate 'Hello, how are you?' to Spanish",
    tools: GeneralTools,
    expectedTool: "translate",
    maxTurns: 10,
  },
  {
    name: "translate_with_source",
    description: "Translate with specified source language",
    systemPrompt: "You are a helpful assistant with access to tools. Use them when needed.",
    userMessage: "Translate 'Bonjour' from French to English",
    tools: GeneralTools,
    expectedTool: "translate",
    maxTurns: 10,
  },
];