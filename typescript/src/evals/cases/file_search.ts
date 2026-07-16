import { EvalCase, ToolDefinition } from "../runner";

export const FileSearchTools: ToolDefinition[] = [
  {
    type: "function",
    function: {
      name: "glob",
      description: "Find files matching a glob pattern in a directory",
      parameters: {
        type: "object",
        properties: {
          pattern: {
            type: "string",
            description: "Glob pattern to match files",
          },
          directory: {
            type: "string",
            description: "Directory to search in",
          },
        },
        required: ["pattern"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "read_file",
      description: "Read contents of a file",
      parameters: {
        type: "object",
        properties: {
          path: {
            type: "string",
            description: "Path to the file to read",
          },
        },
        required: ["path"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "search_files",
      description: "Search for text content in files",
      parameters: {
        type: "object",
        properties: {
          query: {
            type: "string",
            description: "Text to search for",
          },
          path: {
            type: "string",
            description: "Directory path to search in",
          },
        },
        required: ["query"],
      },
    },
  },
];

export const FileSearchCases: EvalCase[] = [
  {
    name: "glob_python_files",
    description: "Find all Python files in the current directory",
    systemPrompt: "You are a helpful assistant with file system access. Use the provided tools to help the user.",
    userMessage: "Find all Python files in the current directory",
    tools: FileSearchTools,
    expectedTool: "glob",
    maxTurns: 10,
  },
  {
    name: "glob_md_files",
    description: "Find all Markdown files",
    systemPrompt: "You are a helpful assistant with file system access. Use the provided tools to help the user.",
    userMessage: "List all markdown files (*.md) in this directory",
    tools: FileSearchTools,
    expectedTool: "glob",
    maxTurns: 10,
  },
  {
    name: "search_code",
    description: "Search for specific code pattern",
    systemPrompt: "You are a helpful assistant with file system access. Use the provided tools to help the user.",
    userMessage: "Search for all files containing 'func main'",
    tools: FileSearchTools,
    expectedTool: "search_files",
    maxTurns: 10,
  },
  {
    name: "read_config",
    description: "Read a configuration file",
    systemPrompt: "You are a helpful assistant with file system access. Use the provided tools to help the user.",
    userMessage: "Read the contents of go.mod",
    tools: FileSearchTools,
    expectedTool: "read_file",
    maxTurns: 10,
  },
];