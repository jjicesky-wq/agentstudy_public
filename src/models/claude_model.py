from __future__ import annotations

from typing import Any, Optional

from anthropic import Anthropic, AsyncAnthropic
from anthropic.types import Message, MessageParam, TextBlock, ToolUseBlock
from pydantic import PrivateAttr

from env_vars import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, USE_MOCK_MODEL
from models.base_model import (
    AIConversationBase,
    AIConversationMessageBase,
    AIConversationToolCall,
    AIModelBase,
)
from tools.base_tool import AIToolBase
from utilities import logger


class ClaudeConversationMessage(AIConversationMessageBase):
    """Claude-specific message implementation."""

    claude_response_message: Optional[Message] = None

    def serialize(self) -> dict[str, Any]:
        """Serialize message for Claude API."""
        if self.role == "system":
            # System messages are handled separately in Claude API
            return {"role": "system", "content": self.content}
        elif self.role == "user":
            # Handle images in user messages (Claude format)
            if self.images:
                content_parts: list[dict[str, Any]] = [
                    {"type": "text", "text": self.content}
                ]
                for image in self.images:
                    # Claude expects images in a specific format
                    if image.startswith("data:image"):
                        # Extract base64 data and media type from data URI
                        # Format: data:image/jpeg;base64,<data>
                        parts = image.split(",", 1)
                        if len(parts) == 2:
                            header = parts[0]  # data:image/jpeg;base64
                            base64_data = parts[1]

                            # Extract media type (e.g., "image/jpeg")
                            media_type = "image/jpeg"  # default
                            if ":" in header and ";" in header:
                                media_type_part = header.split(":")[1].split(";")[0]
                                if media_type_part:
                                    media_type = media_type_part

                            content_parts.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": base64_data,
                                    },
                                }
                            )
                    elif image.startswith("http://") or image.startswith("https://"):
                        # Claude doesn't support direct URLs, need to download and convert to base64
                        # For now, we'll skip URLs and log a warning
                        logger.warning(
                            f"Claude does not support image URLs directly. Please convert {image} to base64."
                        )
                    else:
                        # Assume it's base64 data without prefix
                        content_parts.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",  # default assumption
                                    "data": image,
                                },
                            }
                        )
                return {"role": "user", "content": content_parts}
            else:
                return {"role": "user", "content": self.content}
        elif self.role == "assistant":
            if self.tool_calls:
                # Assistant message with tool calls
                content_blocks = []
                if self.content:
                    content_blocks.append({"type": "text", "text": self.content})
                for tool_call in self.tool_calls:
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.tool_call_id,
                            "name": tool_call.tool_name,
                            "input": tool_call.tool_params,
                        }
                    )
                return {"role": "assistant", "content": content_blocks}
            else:
                return {"role": "assistant", "content": self.content}
        elif self.role == "tool":
            # Tool results in Claude use "user" role with tool_result content
            if not self.tool_calls:
                return {}
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": self.tool_calls[0].tool_call_id,
                        "content": self.content,
                    }
                ],
            }
        else:
            return {}


class ClaudeConversation(AIConversationBase):
    """Claude-specific conversation implementation."""

    def _create_user_prompt_message(
        self, user_prompt: str, images: Optional[list[str]] = None
    ) -> ClaudeConversationMessage:
        """Create user message with proper Claude message type for image support."""
        return ClaudeConversationMessage(
            role="user", content=user_prompt, images=images
        )

    def _create_tool_result_message(
        self, tool_call_id: str, tool_name: str, tool_params: str, tool_result: str
    ) -> ClaudeConversationMessage:
        tool_call = AIConversationToolCall(
            tool_name=tool_name, tool_call_id=tool_call_id, tool_params=tool_params
        )
        return ClaudeConversationMessage(
            role="tool", content=tool_result, tool_calls=[tool_call]
        )

    def generate_image(self, prompt: str) -> bytes:
        """
        Generate an image from a text prompt.

        Note: Claude does not have native image generation capabilities.
        This method raises NotImplementedError.

        Args:
            prompt: Text description of the image to generate

        Raises:
            NotImplementedError: Claude does not support image generation
        """
        raise NotImplementedError(
            "Claude does not support image generation. Use OpenAI DALL-E or other image generation services."
        )

    async def generate_image_async(self, prompt: str) -> bytes:
        """
        Generate an image from a text prompt (async).

        Note: Claude does not have native image generation capabilities.
        This method raises NotImplementedError.

        Args:
            prompt: Text description of the image to generate

        Raises:
            NotImplementedError: Claude does not support image generation
        """
        raise NotImplementedError(
            "Claude does not support image generation. Use OpenAI DALL-E or other image generation services."
        )


class ClaudeModel(AIModelBase):
    """Claude/Anthropic model implementation."""

    _client: Optional[Anthropic] = PrivateAttr(default=None)
    _async_client: Optional[AsyncAnthropic] = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY does not exist in environment variable")

        self.model_class = (
            ANTHROPIC_MODEL or self.model_class or "claude-3-5-sonnet-20241022"
        )
        if not self.model_class:
            raise ValueError("model class is not specified")

    def __del__(self):
        """Clean up async client on deletion."""
        try:
            # Check if private attributes exist before accessing
            if hasattr(self, "_async_client") and self._async_client:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._async_client.close())
                else:
                    asyncio.run(self._async_client.close())
        except (RuntimeError, AttributeError, Exception):
            # Ignore cleanup errors
            pass

    def create_conversation(
        self,
        system_prompt: Optional[str] = None,
        initial_user_prompt: Optional[str] = None,
        tools: Optional[list[AIToolBase]] = None,
        thread_mode: bool = False,
    ) -> ClaudeConversation:
        return ClaudeConversation(
            model=self,
            system_prompt=system_prompt,
            initial_user_prompt=initial_user_prompt,
            tools=tools,
            thread_mode=thread_mode,
        )

    def _convert_message_to_claude_message(
        self, message: AIConversationMessageBase
    ) -> MessageParam | None:
        """Convert base message to Claude message format."""
        serialized = message.serialize()
        if not serialized or "role" not in serialized:
            return None

        # Claude doesn't accept system messages in the messages array
        # They should be passed as the 'system' parameter
        if serialized["role"] == "system":
            return None

        return MessageParam(**serialized)  # type: ignore

    def _get_tool_definitions(
        self, tools: Optional[list[AIToolBase]] = None
    ) -> list[dict[str, Any]]:
        """Convert tools to Claude tool format."""
        if not tools or len(tools) == 0:
            return []

        claude_tools = []
        for tool in tools:
            tool_def = tool.get_tool_definition()
            # Convert from OpenAI format to Claude format
            claude_tool = {
                "name": tool_def["function"]["name"],
                "description": tool_def["function"]["description"],
                "input_schema": tool_def["function"]["parameters"],
            }
            claude_tools.append(claude_tool)

        return claude_tools

    def handle_chat_completion_request(
        self,
        messages: list[AIConversationMessageBase],
        tools: Optional[list[AIToolBase]] = None,
    ) -> ClaudeConversationMessage:
        """Handle synchronous chat completion request."""
        self._create_client()

        # Extract system message if present
        system_message = None
        claude_messages = []
        for message in messages:
            if message.role == "system":
                system_message = message.content
            else:
                message_converted = self._convert_message_to_claude_message(message)
                if message_converted:
                    claude_messages.append(message_converted)

        # Build request parameters
        params: dict[str, Any] = {
            "model": self.model_class,
            "messages": claude_messages,
            "max_tokens": 4096,  # Claude requires max_tokens
        }

        if system_message:
            params["system"] = system_message

        tool_defs = self._get_tool_definitions(tools=tools)
        if tool_defs:
            params["tools"] = tool_defs

        response = self._client.messages.create(**params)  # type: ignore

        # Process response
        content_text = ""
        tool_calls = []

        for block in response.content:
            # Check by type attribute for mock compatibility
            if isinstance(block, TextBlock) or (
                hasattr(block, "type") and block.type == "text"
            ):
                content_text += block.text
            elif isinstance(block, ToolUseBlock) or (
                hasattr(block, "type") and block.type == "tool_use"
            ):
                import json

                tool_calls.append(
                    AIConversationToolCall(
                        tool_call_id=block.id,
                        tool_name=block.name,
                        tool_params=json.dumps(block.input),
                    )
                )

        if tool_calls:
            return ClaudeConversationMessage(
                role="assistant",
                content=content_text,
                tool_calls=tool_calls,
                claude_response_message=response if not USE_MOCK_MODEL else None,
            )
        else:
            return ClaudeConversationMessage(
                role="assistant",
                content=content_text,
                claude_response_message=response if not USE_MOCK_MODEL else None,
            )

    async def handle_chat_completion_request_async(
        self,
        messages: list[AIConversationMessageBase],
        tools: Optional[list[AIToolBase]] = None,
        max_tokens: Optional[int] = None,
    ) -> ClaudeConversationMessage:
        """Handle asynchronous chat completion request."""
        self._create_async_client()

        # Extract system message if present
        system_message = None
        claude_messages = []
        for message in messages:
            if message.role == "system":
                system_message = message.content
            else:
                message_converted = self._convert_message_to_claude_message(message)
                if message_converted:
                    claude_messages.append(message_converted)

        # Build request parameters
        params: dict[str, Any] = {
            "model": self.model_class,
            "messages": claude_messages,
            "max_tokens": max_tokens or 4096,  # Claude requires max_tokens
        }

        if system_message:
            params["system"] = system_message

        tool_defs = self._get_tool_definitions(tools=tools)
        if tool_defs:
            params["tools"] = tool_defs

        response = await self._async_client.messages.create(**params)  # type: ignore

        # Process response
        content_text = ""
        tool_calls = []

        for block in response.content:
            # Check by type attribute for mock compatibility
            if isinstance(block, TextBlock) or (
                hasattr(block, "type") and block.type == "text"
            ):
                content_text += block.text
            elif isinstance(block, ToolUseBlock) or (
                hasattr(block, "type") and block.type == "tool_use"
            ):
                import json

                tool_calls.append(
                    AIConversationToolCall(
                        tool_call_id=block.id,
                        tool_name=block.name,
                        tool_params=json.dumps(block.input),
                    )
                )

        if tool_calls:
            return ClaudeConversationMessage(
                role="assistant",
                content=content_text,
                tool_calls=tool_calls,
                claude_response_message=response if not USE_MOCK_MODEL else None,
            )
        else:
            return ClaudeConversationMessage(
                role="assistant",
                content=content_text,
                claude_response_message=response if not USE_MOCK_MODEL else None,
            )

    def handle_image_request(
        self,
        prompt: str,
        size: Optional[str] = None,
        quality: Optional[str] = None,
        style: Optional[str] = None,
    ) -> bytes:
        """
        Handle image generation request.

        Note: Claude does not have native image generation capabilities.
        This method raises NotImplementedError.

        Args:
            prompt: Text description of the image to generate
            size: Image size (ignored)
            quality: Quality setting (ignored)
            style: Style setting (ignored)

        Raises:
            NotImplementedError: Claude does not support image generation
        """
        raise NotImplementedError(
            "Claude does not support image generation. Use OpenAI DALL-E or other image generation services."
        )

    async def handle_image_request_async(
        self,
        prompt: str,
        size: Optional[str] = None,
        quality: Optional[str] = None,
        style: Optional[str] = None,
    ) -> bytes:
        """
        Handle image generation request (async).

        Note: Claude does not have native image generation capabilities.
        This method raises NotImplementedError.

        Args:
            prompt: Text description of the image to generate
            size: Image size (ignored)
            quality: Quality setting (ignored)
            style: Style setting (ignored)

        Raises:
            NotImplementedError: Claude does not support image generation
        """
        raise NotImplementedError(
            "Claude does not support image generation. Use OpenAI DALL-E or other image generation services."
        )

    async def generate_embedding(self, content: str) -> list[float]:
        """
        Generate an embedding vector from the given content.

        Note: Claude does not natively support embeddings. This implementation
        falls back to using OpenAI's embedding API.

        Args:
            content: The text content to generate an embedding for

        Returns:
            List of floats representing the embedding vector

        Raises:
            NotImplementedError: Claude does not support embeddings natively
        """
        # Claude doesn't have native embedding support
        # Option 1: Raise NotImplementedError
        # Option 2: Fallback to OpenAI embeddings
        logger.warning(
            "Claude does not support native embeddings. Falling back to OpenAI text-embedding-3-small"
        )

        from openai import AsyncOpenAI

        from env_vars import OPENAI_API_KEY

        if not OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY required for embedding generation (Claude fallback)"
            )

        async_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        try:
            response = await async_client.embeddings.create(
                model="text-embedding-3-small",
                input=content,
            )
            embedding = response.data[0].embedding
            logger.info(
                f"Generated embedding using OpenAI fallback: {len(embedding)} dimensions"
            )
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding with OpenAI fallback: {str(e)}")
            raise

    def estimate_token_count(self, text: str) -> int:
        """
        Estimate the number of tokens in a text string.

        Claude uses a similar tokenization to GPT models, so we use
        a character-based estimation (roughly 1 token per 4 characters).

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated number of tokens
        """
        # Claude's tokenization is similar to OpenAI's
        # Use character-based estimation: roughly 1 token per 4 characters
        return len(text) // 4

    def initialize_thread(
        self,
        system_prompt: Optional[str] = None,
        initial_user_prompt: Optional[str] = None,
        tools: Optional[list[AIToolBase]] = None,
    ) -> str:
        """
        Initialize a thread for conversation.

        Note: Claude doesn't have a separate thread/responses API like OpenAI.
        This method returns a dummy thread ID for compatibility with the base API.
        Thread context is maintained through the full message history in the conversation.

        Args:
            system_prompt: Optional system prompt (unused, passed via messages)
            initial_user_prompt: Optional initial prompt (unused, passed via messages)
            tools: Optional list of tools (unused, passed with each request)

        Returns:
            Dummy thread ID (Claude doesn't use thread IDs)
        """
        import uuid

        # Return a dummy thread ID for API compatibility
        # Claude maintains context through message history, not thread IDs
        thread_id = f"claude-thread-{uuid.uuid4()}"
        logger.info(f"Claude thread initialized (dummy ID): {thread_id}")
        return thread_id

    def handle_thread_request(
        self,
        messages: list[AIConversationMessageBase],
        tools: Optional[list[AIToolBase]] = None,
        previous_response_id: Optional[str] = None,
    ) -> ClaudeConversationMessage:
        """
        Handle thread request using Claude's messages API.

        Note: Claude doesn't have a separate thread/responses API like OpenAI.
        Thread mode is implemented by maintaining message history in the conversation.
        The previous_response_id parameter is ignored as Claude identifies context
        through the full message history.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools
            previous_response_id: Ignored (Claude uses message history for context)

        Returns:
            ClaudeConversationMessage with response content and tool calls
        """
        # Claude handles threading through message history, so we just use the regular
        # chat completion with the full message history
        result = self.handle_chat_completion_request(messages=messages, tools=tools)
        return result

    async def handle_thread_request_async(
        self,
        messages: list[AIConversationMessageBase],
        tools: Optional[list[AIToolBase]] = None,
        previous_response_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> ClaudeConversationMessage:
        """
        Handle thread request asynchronously using Claude's messages API.

        Note: Claude doesn't have a separate thread/responses API like OpenAI.
        Thread mode is implemented by maintaining message history in the conversation.
        The previous_response_id parameter is ignored as Claude identifies context
        through the full message history.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools
            previous_response_id: Ignored (Claude uses message history for context)
            max_tokens: Optional maximum tokens for response

        Returns:
            ClaudeConversationMessage with response content and tool calls
        """
        # Claude handles threading through message history, so we just use the regular
        # async chat completion with the full message history
        result = await self.handle_chat_completion_request_async(
            messages=messages, tools=tools, max_tokens=max_tokens
        )
        return result

    def get_max_context_tokens(self) -> int:
        """
        Get the maximum context token limit for the model.

        Returns:
            Maximum number of tokens the model can handle in its context
        """
        # Claude model context limits
        model_limits = {
            "claude-3-5-sonnet-20241022": 200000,
            "claude-3-5-sonnet-20240620": 200000,
            "claude-3-opus-20240229": 200000,
            "claude-3-sonnet-20240229": 200000,
            "claude-3-haiku-20240307": 200000,
            "claude-2.1": 200000,
            "claude-2.0": 100000,
            "claude-instant-1.2": 100000,
        }

        # Return known limit or default to 200000 for Claude 3 models
        return model_limits.get(self.model_class, 200000)

    def _create_client(self):
        if not self._client:
            if USE_MOCK_MODEL:
                from utilities.mock_model_client import MockAnthropic

                self._client = MockAnthropic(api_key=ANTHROPIC_API_KEY)  # type: ignore
                logger.info("Using MockAnthropic client (USE_MOCK_MODEL=true)")
            else:
                self._client = Anthropic(api_key=ANTHROPIC_API_KEY)

    def _create_async_client(self):
        if not self._async_client:
            if USE_MOCK_MODEL:
                from utilities.mock_model_client import MockAnthropic

                self._async_client = MockAnthropic(api_key=ANTHROPIC_API_KEY, async_mode=True)  # type: ignore
                logger.info("Using MockAnthropic async client (USE_MOCK_MODEL=true)")
            else:
                self._async_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


if __name__ == "__main__":
    import asyncio

    async def interactive_mode():
        current_conversation = None
        model = ClaudeModel(model_class="claude-3-5-sonnet-20241022")
        print("Start Claude model in interactive mode (threaded conversation)!")
        while True:
            user_prompt: str = ""
            if current_conversation:
                print("")
                user_prompt = input("> ")
                if user_prompt.lower() == "exit":
                    exit()
            if not current_conversation or user_prompt.lower() == "new":
                current_conversation = model.create_conversation(
                    system_prompt="You are a helpful agent that answers any user questions",
                    thread_mode=True,  # Enable threaded conversation mode
                )
                print(
                    """
*******************************************************************************
*                    New threaded conversation started!                       *
* Commands:                                                                   *
*   exit  - quit the interactive mode                                         *
*   new   - start a new conversation                                          *
*******************************************************************************
"""
                )
                continue
            # Use async threaded conversation
            response = await current_conversation.run_chat_completion_async(
                user_prompt=user_prompt
            )
            print(f"Agent: {response}")

    asyncio.run(interactive_mode())
