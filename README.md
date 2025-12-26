# Introduction

This is a sample project that introduces basic LLM agent concepts and provides a sample implementation that calls the LLM's APIs to handle conversation, tool calling, image OCR, etc.

# Set up

To set up the environment for this project, follow the steps below:

1. Install Python 3.10+
2. Initialize a virtual environment by:
    - In bash/cmd, navigate to the root of this project (not `src`)
    - Run `python -m venv venv`
Í
    This will create a folder called "venv" under the root of this project.
3. Activate the virtual environment (do this every time when you resume work on this project):
    - In bash/cmd, navigate to the root of this project (not `src`)
    - Mac/Linux: `source ./venv/bin/activate`
    - Windows: `venv\scripts\activate.bat`
4. Install the dependencies of this project:
    - In bash/cmd, navigate to the root of this project (not `src`)
    - Run `pip install -r requirements.txt`

At this point, the working environment is configured properly.

# Environment Variables

Before being able to make LLM API calls, you then need to obtain API key for the LLM model that you plan to use and configure the environment variables accordingly.

## OpenAI

Go to [OpenAI API](https://openai.com/api/), select log in on the top right corner and log in to "API Platform" (sign up if needed). Then click on settings on the top right corner and you will see the API key on the left navigation bar. Follow the instruction there to set up.

## Anthropic 
Go to [Claude Developer Platform](https://platform.claude.com/login?returnTo=%2F%3F), log in/register. Once logged in, you will see the "Get API Key" button. Follow the instruction there to set up.

## Environment File Setup
Once you get one or more of these API keys, you need to create a duplicate of the `.env_template` file located at the root of this project, and rename the new file to `.env`. Inside the `.env` file, you will see:

```
# ============================================
# REQUIRED - OpenAI API
# ============================================
# Get your API key from: https://platform.openai.com/api-keys
OPENAI_API_KEY=

# Optional: Specify which model to use (default: gpt-4)
# OPENAI_MODEL=gpt-4

# ============================================
# OPTIONAL - Azure OpenAI (Alternative to OpenAI)
# ============================================
# Use Azure OpenAI instead of standard OpenAI API
# Get credentials from Azure Portal: https://portal.azure.com
# AZURE_OPENAI_API_KEY=
# AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
# AZURE_OPENAI_DEPLOYMENT=your-deployment-name
# AZURE_OPENAI_API_VERSION=2024-02-15-preview

# ============================================
# OPTIONAL - Anthropic/Claude API
# ============================================
# ANTHROPIC_API_KEY=
# ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

Set the appropriate API key and models to be able to make API calls.

# Models

This project provides a sample implementation of the LLM models that abstracts the functionalities that LLM supports.

## Architecture

The models are organized using an abstract base class pattern in [src/models/](src/models/):

- **[base_model.py](src/models/base_model.py)** - Defines the abstract base classes:
  - `AIModelBase` - Base class for all LLM providers with abstract methods for chat completion, image generation, embeddings, token estimation, and thread management
  - `AIConversationBase` - Manages conversation state, message history, and tool calling loop (both sync and async)
  - `AIConversationMessageBase` - Represents individual messages with role, content, images, and tool calls
  - `AIConversationToolCall` - Represents a tool call request from the model

## Supported Providers

### OpenAI ([openai_model.py](src/models/openai_model.py))
- Chat completions via `chat.completions.create()`
- Thread mode using OpenAI's Responses API for persistent conversations
- Image generation via DALL-E 3 (with fallback to legacy API)
- Embeddings via `text-embedding-3-small`
- Token counting using `tiktoken`
- Vision support (accepts image URLs and base64-encoded images)

### Claude/Anthropic ([claude_model.py](src/models/claude_model.py))
- Chat completions via Anthropic's Messages API
- Thread mode emulated through message history (Claude doesn't have a native thread API)
- Vision support with base64-encoded images
- Token estimation using character-based approximation (~1 token per 4 chars)
- Falls back to OpenAI for embeddings (Claude doesn't support native embeddings)
- Image generation not supported (raises `NotImplementedError`)

### Azure OpenAI ([az_openai_model.py](src/models/az_openai_model.py))
- Extends `OpenAIModel` with Azure-specific client configuration
- Uses `AzureOpenAI` and `AsyncAzureOpenAI` clients
- Requires Azure-specific environment variables (endpoint, deployment, API version)
- Inherits all OpenAI functionality (chat, tools, images, embeddings)

## Key Features

| Feature | OpenAI | Claude | Azure OpenAI |
|---------|--------|--------|--------------|
| Chat Completion | ✅ | ✅ | ✅ |
| Tool Calling | ✅ | ✅ | ✅ |
| Thread Mode | ✅ (Responses API) | ✅ (emulated) | ✅ |
| Image Generation | ✅ (DALL-E 3) | ❌ | ✅ |
| Vision/OCR | ✅ | ✅ | ✅ |
| Embeddings | ✅ | ✅ (via OpenAI fallback) | ✅ |
| Async Support | ✅ | ✅ | ✅ |
| Mock Mode | ✅ | ✅ | ✅ |

## Usage

```python
from models.openai_model import OpenAIModel
from models.claude_model import ClaudeModel

# Create a model instance
model = OpenAIModel(model_class="gpt-4o")

# Create a conversation with system prompt and tools
conversation = model.create_conversation(
    system_prompt="You are a helpful assistant",
    tools=[my_tool],
    thread_mode=True  # Enable persistent threading
)

# Run chat completion (handles tool calling loop automatically)
response = conversation.run_chat_completion(user_prompt="Hello!")

# Async version
response = await conversation.run_chat_completion_async(user_prompt="Hello!")
```

# Tools

Tools enable LLM agents to perform actions beyond text generation, such as calling APIs, executing code, or interacting with external systems. This project provides a base class for creating custom tools that can be used with any of the supported model providers.

## Architecture

The tool system is defined in [src/tools/base_tool.py](src/tools/base_tool.py):

- **`AIToolBase`** - Abstract base class for all tools with the following key attributes:
  - `name` - Unique identifier for the tool
  - `description` - Human-readable description (used by the LLM to understand when to use the tool)
  - `parameters` - JSON Schema defining the expected input parameters
  - `strict` - Whether parameter validation should be enforced (default: `True`)

## Creating a Custom Tool

To create a custom tool, extend `AIToolBase` and implement the `_run` method:

```python
from tools.base_tool import AIToolBase
import json

class WeatherTool(AIToolBase):
    name: str = "get_weather"
    description: str = "Get the current weather for a specified city"
    parameters: dict = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "The city name to get weather for"
            },
            "unit": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "Temperature unit"
            }
        },
        "required": ["city"]
    }

    def _run(self, params: str) -> str:
        """Execute the tool with the given parameters (as JSON string)."""
        args = json.loads(params)
        city = args["city"]
        unit = args.get("unit", "celsius")

        # Your actual implementation here (e.g., call a weather API)
        return f"The weather in {city} is 22°{unit[0].upper()}"

    async def _run_async(self, params: str) -> str:
        """Optional: Override for true async implementation."""
        # Default falls back to sync _run in executor
        return self._run(params)
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Sync & Async Support** | Both `run_tool()` and `run_tool_async()` methods available |
| **Result Caching** | Override `use_cached_result()` to return `True` for deterministic tools |
| **Override Handlers** | Use `override_run` or `override_run_async` to inject custom behavior |
| **Auto Tool Loop** | The conversation classes automatically handle the tool calling loop |

## Using Tools with Models

```python
from models.openai_model import OpenAIModel
from my_tools import WeatherTool, CalculatorTool

# Create model and tools
model = OpenAIModel(model_class="gpt-4o")
tools = [WeatherTool(), CalculatorTool()]

# Create conversation with tools
conversation = model.create_conversation(
    system_prompt="You are a helpful assistant with access to weather and calculator tools.",
    tools=tools
)

# The model will automatically use tools when appropriate
response = conversation.run_chat_completion(
    user_prompt="What's the weather in Tokyo and what is 15% of 250?"
)
# The conversation handles:
# 1. Model decides to call tools
# 2. Tools are executed with provided parameters
# 3. Results are sent back to the model
# 4. Model generates final response
```

## Tool Definition Format

Tools are converted to the OpenAI function calling format internally:

```python
{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a specified city",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "The city name"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
            },
            "required": ["city"],
            "additionalProperties": False
        },
        "strict": True
    }
}
```

For Claude, tools are automatically converted to Anthropic's tool format by the `ClaudeModel` class.

