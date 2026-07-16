package evals

var GeneralTools = []ToolDefinition{
	{
		Type: "function",
		Function: ToolFunc{
			Name:        "calculator",
			Description: "Perform mathematical calculations",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"expression": map[string]interface{}{
						"type":        "string",
						"description": "Mathematical expression to evaluate",
					},
				},
				"required": []string{"expression"},
			},
		},
	},
	{
		Type: "function",
		Function: ToolFunc{
			Name:        "get_weather",
			Description: "Get weather information for a location",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"location": map[string]interface{}{
						"type":        "string",
						"description": "City name",
					},
					"units": map[string]interface{}{
						"type":        "string",
						"enum":        []string{"celsius", "fahrenheit"},
						"description": "Temperature units",
					},
				},
				"required": []string{"location"},
			},
		},
	},
	{
		Type: "function",
		Function: ToolFunc{
			Name:        "translate",
			Description: "Translate text between languages",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"text": map[string]interface{}{
						"type":        "string",
						"description": "Text to translate",
					},
					"target_lang": map[string]interface{}{
						"type":        "string",
						"description": "Target language code",
					},
					"source_lang": map[string]interface{}{
						"type":        "string",
						"description": "Source language code (optional, auto-detect if not provided)",
					},
				},
				"required": []string{"text", "target_lang"},
			},
		},
	},
}

var FileSearchTools = []ToolDefinition{
	{
		Type: "function",
		Function: ToolFunc{
			Name:        "glob",
			Description: "Find files matching a glob pattern in a directory",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"pattern": map[string]interface{}{
						"type":        "string",
						"description": "Glob pattern to match files",
					},
					"directory": map[string]interface{}{
						"type":        "string",
						"description": "Directory to search in",
					},
				},
				"required": []string{"pattern"},
			},
		},
	},
	{
		Type: "function",
		Function: ToolFunc{
			Name:        "read_file",
			Description: "Read contents of a file",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{
						"type":        "string",
						"description": "Path to the file to read",
					},
				},
				"required": []string{"path"},
			},
		},
	},
	{
		Type: "function",
		Function: ToolFunc{
			Name:        "search_files",
			Description: "Search for text content in files",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"query": map[string]interface{}{
						"type":        "string",
						"description": "Text to search for",
					},
					"path": map[string]interface{}{
						"type":        "string",
						"description": "Directory path to search in",
					},
				},
				"required": []string{"query"},
			},
		},
	},
}

var GeneralCases = []EvalCase{
	{
		Name:         "calculator_add",
		Description:  "Simple addition calculation",
		SystemPrompt: "You are a helpful assistant with access to tools. Use them when needed.",
		UserMessage:  "What is 123 + 456?",
		Tools:        GeneralTools,
		ExpectedTool: "calculator",
		MaxTurns:     10,
	},
	{
		Name:         "calculator_complex",
		Description:  "Complex mathematical expression",
		SystemPrompt: "You are a helpful assistant with access to tools. Use them when needed.",
		UserMessage:  "Calculate (15 * 8) + (100 / 4) - 50",
		Tools:        GeneralTools,
		ExpectedTool: "calculator",
		MaxTurns:     10,
	},
	{
		Name:         "get_weather",
		Description:  "Get weather for a city",
		SystemPrompt: "You are a helpful assistant with access to tools. Use them when needed.",
		UserMessage:  "What's the weather like in Tokyo?",
		Tools:        GeneralTools,
		ExpectedTool: "get_weather",
		MaxTurns:     10,
	},
	{
		Name:         "translate_english_to_spanish",
		Description:  "Translate text to Spanish",
		SystemPrompt: "You are a helpful assistant with access to tools. Use them when needed.",
		UserMessage:  "Translate 'Hello, how are you?' to Spanish",
		Tools:        GeneralTools,
		ExpectedTool: "translate",
		MaxTurns:     10,
	},
	{
		Name:         "translate_with_source",
		Description:  "Translate with specified source language",
		SystemPrompt: "You are a helpful assistant with access to tools. Use them when needed.",
		UserMessage:  "Translate 'Bonjour' from French to English",
		Tools:        GeneralTools,
		ExpectedTool: "translate",
		MaxTurns:     10,
	},
}

var FileSearchCases = []EvalCase{
	{
		Name:         "glob_python_files",
		Description:  "Find all Python files in the current directory",
		SystemPrompt: "You are a helpful assistant with file system access. Use the provided tools to help the user.",
		UserMessage:  "Find all Python files in the current directory",
		Tools:        FileSearchTools,
		ExpectedTool: "glob",
		MaxTurns:     10,
	},
	{
		Name:         "glob_md_files",
		Description:  "Find all Markdown files",
		SystemPrompt: "You are a helpful assistant with file system access. Use the provided tools to help the user.",
		UserMessage:  "List all markdown files (*.md) in this directory",
		Tools:        FileSearchTools,
		ExpectedTool: "glob",
		MaxTurns:     10,
	},
	{
		Name:         "search_code",
		Description:  "Search for specific code pattern",
		SystemPrompt: "You are a helpful assistant with file system access. Use the provided tools to help the user.",
		UserMessage:  "Search for all files containing 'func main'",
		Tools:        FileSearchTools,
		ExpectedTool: "search_files",
		MaxTurns:     10,
	},
	{
		Name:         "read_config",
		Description:  "Read a configuration file",
		SystemPrompt: "You are a helpful assistant with file system access. Use the provided tools to help the user.",
		UserMessage:  "Read the contents of go.mod",
		Tools:        FileSearchTools,
		ExpectedTool: "read_file",
		MaxTurns:     10,
	},
}
