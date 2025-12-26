from __future__ import annotations

from typing import Any, Optional

from openai import AsyncOpenAI, OpenAI
from openai.types.chat.chat_completion_assistant_message_param import (
    ChatCompletionAssistantMessageParam,
)
from openai.types.chat.chat_completion_function_tool_param import (
    ChatCompletionFunctionToolParam,
)
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
)
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_tool_message_param import (
    ChatCompletionToolMessageParam,
)
from openai.types.chat.chat_completion_tool_union_param import (
    ChatCompletionToolUnionParam,
)
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)
from openai.types.responses.function_tool_param import FunctionToolParam
from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall
from openai.types.responses.response_function_tool_call_output_item import (
    ResponseFunctionToolCallOutputItem,
)
from pydantic import PrivateAttr

from env_vars import OPENAI_API_KEY, OPENAI_MODEL, USE_MOCK_MODEL
from models.base_model import (
    AIConversationBase,
    AIConversationMessageBase,
    AIConversationToolCall,
    AIModelBase,
)
from tools.base_tool import AIToolBase
from utilities import logger


class OpenAIConversationMessage(AIConversationMessageBase):
    openai_response_message: Optional[ChatCompletionMessage] = None

    def serialize(self) -> dict[str, Any]:
        if self.role == "system":
            return super().serialize()
        elif self.role == "user":
            # Handle images in user messages
            if self.images:
                content_parts: list[dict[str, Any]] = [
                    {"type": "text", "text": self.content}
                ]
                for image in self.images:
                    # Support both URLs and base64-encoded images
                    if image.startswith("data:"):
                        # Base64-encoded image
                        content_parts.append(
                            {"type": "image_url", "image_url": {"url": image}}
                        )
                    elif image.startswith("http://") or image.startswith("https://"):
                        # URL
                        content_parts.append(
                            {"type": "image_url", "image_url": {"url": image}}
                        )
                    else:
                        # Assume base64 without prefix, add prefix
                        image_url = f"data:image/jpeg;base64,{image}"
                        content_parts.append(
                            {"type": "image_url", "image_url": {"url": image_url}}
                        )
                return {"role": self.role, "content": content_parts}
            else:
                return super().serialize()
        elif self.role == "tool":
            if not self.tool_calls:
                return {}
            return {
                "role": self.role,
                "tool_call_id": self.tool_calls[0].tool_call_id,
                "name": self.tool_calls[0].tool_name,
                "content": self.content,
            }
        elif self.role == "function":
            if not self.tool_calls:
                return {}
            return {
                "call_id": self.tool_calls[0].tool_call_id,
                "output": self.content,
                "type": "function_call_output",
            }
        elif self.openai_response_message:
            return self.openai_response_message.model_dump()
        else:
            return {}


class OpenAIConversation(AIConversationBase):
    def _create_tool_result_message(
        self, tool_call_id: str, tool_name: str, tool_params: str, tool_result: str
    ) -> OpenAIConversationMessage:
        tool_call = AIConversationToolCall(
            tool_name=tool_name, tool_call_id=tool_call_id, tool_params=tool_params
        )
        if self.thread_mode:
            return OpenAIConversationMessage(
                role="function", content=tool_result, tool_calls=[tool_call]
            )
        else:
            return OpenAIConversationMessage(
                role="tool", content=tool_result, tool_calls=[tool_call]
            )

    def generate_image(self, prompt: str) -> bytes:
        """
        Generate an image from a text prompt using the model's image generation API.

        Args:
            prompt: Text description of the image to generate

        Returns:
            Image bytes (PNG format)
        """
        return self.model.handle_image_request(prompt=prompt)

    async def generate_image_async(self, prompt: str) -> bytes:
        """
        Generate an image from a text prompt using the model's image generation API (async).

        Args:
            prompt: Text description of the image to generate

        Returns:
            Image bytes (PNG format)
        """
        return await self.model.handle_image_request_async(prompt=prompt)


class OpenAIModel(AIModelBase):
    _client: Optional[OpenAI] = PrivateAttr(default=None)
    _async_client: Optional[AsyncOpenAI] = PrivateAttr(default=None)
    _encoding: Optional[Any] = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY does not exist in environment variable")

        self.model_class = OPENAI_MODEL or self.model_class
        if not self.model_class:
            raise ValueError("model class is not specified")

        # tiktoken will be imported when needed in estimate_token_count

    def __del__(self):
        """Clean up async client on deletion, handling event loop closure gracefully."""
        if self._async_client:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, schedule cleanup
                    loop.create_task(self._async_client.close())
                else:
                    # If loop is not running, run cleanup synchronously
                    asyncio.run(self._async_client.close())
            except RuntimeError:
                # Event loop is closed, ignore the error
                # The httpx client will try to close but fail gracefully
                pass
            except Exception:
                # Ignore any other cleanup errors
                pass

    def create_conversation(
        self,
        system_prompt: Optional[str] = None,
        initial_user_prompt: Optional[str] = None,
        tools: Optional[list[AIToolBase]] = None,
        thread_mode: bool = False,
    ) -> OpenAIConversation:
        return OpenAIConversation(
            model=self,
            system_prompt=system_prompt,
            initial_user_prompt=initial_user_prompt,
            tools=tools,
            thread_mode=thread_mode,
        )

    def _convert_message_to_openai_message(
        self, message: AIConversationMessageBase
    ) -> ChatCompletionMessageParam | ResponseFunctionToolCallOutputItem | None:
        serialized = message.serialize()
        if message.role == "system":
            return ChatCompletionSystemMessageParam(**serialized)
        elif message.role == "user":
            return ChatCompletionUserMessageParam(**serialized)
        elif message.role == "assistant":
            return ChatCompletionAssistantMessageParam(**serialized)
        elif message.role == "tool":
            return ChatCompletionToolMessageParam(**serialized)
        elif message.role == "function":
            return ResponseFunctionToolCallOutputItem(**serialized)
        else:
            logger.warning(f"Message role {message.role} not valid for convert")
            return None

    def _get_tool_definitions(
        self, tools: Optional[list[AIToolBase]] = None
    ) -> list[ChatCompletionToolUnionParam]:
        if not tools or len(tools) == 0:
            return []
        return [
            ChatCompletionFunctionToolParam(**t.get_tool_definition()) for t in tools
        ]

    def handle_chat_completion_request(
        self,
        messages: list[AIConversationMessageBase],
        tools: Optional[list[AIToolBase]] = None,
    ) -> OpenAIConversationMessage:
        self._create_client()
        messages_serialized = []
        for message in messages:
            message_converted = self._convert_message_to_openai_message(message=message)
            if not message_converted:
                continue
            messages_serialized += [message_converted]
        response = self._client.chat.completions.create(  # type: ignore
            model=self.model_class,
            messages=messages_serialized,
            tools=self._get_tool_definitions(tools=tools),
        )
        response_message = response.choices[0].message
        if response_message.tool_calls:
            tool_calls = []
            for tool_call in response_message.tool_calls:
                if not isinstance(tool_call, ChatCompletionMessageFunctionToolCall):
                    continue
                tool_name = tool_call.function.name
                tool_params = tool_call.function.arguments
                tool_call_id = tool_call.id
                tool_calls += [
                    AIConversationToolCall(
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        tool_params=tool_params,
                    )
                ]
            result_message = OpenAIConversationMessage(
                role="assistant",
                tool_calls=tool_calls,
                openai_response_message=response_message
                if not USE_MOCK_MODEL
                else None,
                content=response_message.content or "",
            )
        else:
            result_message = OpenAIConversationMessage(
                role="assistant",
                content=response_message.content or "",
                openai_response_message=response_message
                if not USE_MOCK_MODEL
                else None,
            )
        return result_message

    async def handle_chat_completion_request_async(
        self,
        messages: list[AIConversationMessageBase],
        tools: Optional[list[AIToolBase]] = None,
        max_tokens: Optional[int] = None,
    ) -> OpenAIConversationMessage:
        self._create_async_client()
        messages_serialized = []
        for message in messages:
            message_converted = self._convert_message_to_openai_message(message=message)
            if not message_converted:
                continue
            messages_serialized += [message_converted]

        # Build completion parameters
        completion_params = {
            "model": self.model_class,
            "messages": messages_serialized,
            "tools": self._get_tool_definitions(tools=tools),
        }
        if max_tokens is not None:
            completion_params["max_tokens"] = max_tokens

        response = await self._async_client.chat.completions.create(**completion_params)  # type: ignore
        response_message = response.choices[0].message
        if response_message.tool_calls:
            tool_calls = []
            for tool_call in response_message.tool_calls:
                if not isinstance(tool_call, ChatCompletionMessageFunctionToolCall):
                    continue
                tool_name = tool_call.function.name
                tool_params = tool_call.function.arguments
                tool_call_id = tool_call.id
                tool_calls += [
                    AIConversationToolCall(
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        tool_params=tool_params,
                    )
                ]
            result_message = OpenAIConversationMessage(
                role="assistant",
                tool_calls=tool_calls,
                openai_response_message=response_message
                if not USE_MOCK_MODEL
                else None,
                content=response_message.content or "",
            )
        else:
            result_message = OpenAIConversationMessage(
                role="assistant",
                content=response_message.content or "",
                openai_response_message=response_message
                if not USE_MOCK_MODEL
                else None,
            )
        return result_message

    def handle_image_request(
        self,
        prompt: str,
        size: Optional[str] = None,
        quality: Optional[str] = None,
        style: Optional[str] = None,
    ) -> bytes:
        """
        Handle image generation request using OpenAI's image generation tool (synchronous).

        Uses the newer OpenAI API pattern with responses.create() and image_generation tool.

        Args:
            prompt: Text description of the image to generate
            size: Image size (e.g., "1024x1024", "1792x1024", "1024x1792") - currently unused
            quality: Quality setting ("standard" or "hd") - currently unused
            style: Style setting ("natural" or "vivid") - currently unused

        Returns:
            Image bytes (PNG format)

        Raises:
            ValueError: If prompt is empty or invalid parameters
            Exception: If API request fails
        """
        if not prompt:
            raise ValueError("Prompt cannot be empty")

        self._create_client()
        logger.info(f"Generating image with prompt: {prompt[:100]}...")

        try:
            # Use the newer responses API with image_generation tool
            response = self._client.responses.create(  # type: ignore
                model=self.model_class,
                input=prompt,
                tools=[{"type": "image_generation"}],
            )

            # Extract base64-encoded image from response
            image_data = [
                output.result
                for output in response.output
                if output.type == "image_generation_call"
            ]

            if image_data:
                import base64

                image_base64 = image_data[0]
                image_bytes = base64.b64decode(image_base64)  # type: ignore
                logger.info(f"Successfully generated image ({len(image_bytes)} bytes)")
                return image_bytes
            else:
                raise Exception("No image_generation_call output in response")

        except AttributeError:
            # Fallback to older images.generate API if responses API not available
            logger.warning(
                "responses.create() not available, falling back to images.generate()"
            )
            return self._handle_image_request_legacy(prompt, size, quality, style)

        except Exception as e:
            logger.error(f"Failed to generate image: {str(e)}")
            raise

    def _handle_image_request_legacy(
        self,
        prompt: str,
        size: Optional[str] = None,
        quality: Optional[str] = None,
        style: Optional[str] = None,
    ) -> bytes:
        """
        Legacy fallback for image generation using DALL-E API.

        Args:
            prompt: Text description of the image to generate
            size: Image size (e.g., "1024x1024", "1792x1024", "1024x1792")
            quality: Quality setting ("standard" or "hd")
            style: Style setting ("natural" or "vivid")

        Returns:
            Image bytes (PNG format)
        """
        import base64

        # Ensure client is initialized
        self._create_client()

        # Build request parameters
        params: dict[str, Any] = {
            "model": "dall-e-3",  # Use DALL-E 3 by default
            "prompt": prompt,
            "n": 1,  # Generate 1 image
            "response_format": "b64_json",  # Get base64-encoded image
        }

        if size:
            params["size"] = size
        if quality:
            params["quality"] = quality
        if style:
            params["style"] = style

        response = self._client.images.generate(**params)  # type: ignore

        # Extract base64-encoded image from response
        if response.data and len(response.data) > 0:
            image_data = response.data[0]
            if hasattr(image_data, "b64_json") and image_data.b64_json:
                image_bytes = base64.b64decode(image_data.b64_json)
                return image_bytes
            else:
                raise Exception("No b64_json data in response")
        else:
            raise Exception("No image data in response")

    async def handle_image_request_async(
        self,
        prompt: str,
        size: Optional[str] = None,
        quality: Optional[str] = None,
        style: Optional[str] = None,
    ) -> bytes:
        """
        Handle image generation request using OpenAI's image generation tool (async).

        Uses the newer OpenAI API pattern with responses.create() and image_generation tool.

        Args:
            prompt: Text description of the image to generate
            size: Image size (e.g., "1024x1024", "1792x1024", "1024x1792") - currently unused
            quality: Quality setting ("standard" or "hd") - currently unused
            style: Style setting ("natural" or "vivid") - currently unused

        Returns:
            Image bytes (PNG format)

        Raises:
            ValueError: If prompt is empty or invalid parameters
            Exception: If API request fails
        """
        if not prompt:
            raise ValueError("Prompt cannot be empty")

        self._create_async_client()

        logger.info(f"Generating image (async) with prompt: {prompt[:100]}...")

        try:
            # Use the newer responses API with image_generation tool
            response = await self._async_client.responses.create(  # type: ignore
                model=self.model_class,
                input=prompt,
                tools=[{"type": "image_generation"}],
            )

            # Extract base64-encoded image from response
            image_data = [
                output.result
                for output in response.output
                if output.type == "image_generation_call"
            ]

            if image_data:
                import base64

                image_base64 = image_data[0]
                image_bytes = base64.b64decode(image_base64)  # type: ignore
                logger.info(f"Successfully generated image ({len(image_bytes)} bytes)")
                return image_bytes
            else:
                raise Exception("No image_generation_call output in response")

        except AttributeError:
            # Fallback to older images.generate API if responses API not available
            logger.warning(
                "responses.create() not available, falling back to images.generate()"
            )
            return await self._handle_image_request_async_legacy(
                prompt, size, quality, style
            )

        except Exception as e:
            logger.error(f"Failed to generate image: {str(e)}")
            raise

    async def _handle_image_request_async_legacy(
        self,
        prompt: str,
        size: Optional[str] = None,
        quality: Optional[str] = None,
        style: Optional[str] = None,
    ) -> bytes:
        """
        Legacy fallback for async image generation using DALL-E API.

        Args:
            prompt: Text description of the image to generate
            size: Image size (e.g., "1024x1024", "1792x1024", "1024x1792")
            quality: Quality setting ("standard" or "hd")
            style: Style setting ("natural" or "vivid")

        Returns:
            Image bytes (PNG format)
        """
        import base64

        # Ensure async client is initialized
        self._create_async_client()

        # Build request parameters
        params: dict[str, Any] = {
            "model": "dall-e-3",  # Use DALL-E 3 by default
            "prompt": prompt,
            "n": 1,  # Generate 1 image
            "response_format": "b64_json",  # Get base64-encoded image
        }

        if size:
            params["size"] = size
        if quality:
            params["quality"] = quality
        if style:
            params["style"] = style

        response = await self._async_client.images.generate(**params)  # type: ignore

        # Extract base64-encoded image from response
        if response.data and len(response.data) > 0:
            image_data = response.data[0]
            if hasattr(image_data, "b64_json") and image_data.b64_json:
                image_bytes = base64.b64decode(image_data.b64_json)
                return image_bytes
            else:
                raise Exception("No b64_json data in response")
        else:
            raise Exception("No image data in response")

    async def generate_embedding(self, content: str) -> list[float]:
        """
        Generate an embedding vector from the given content using OpenAI's embedding API.

        Args:
            content: The text content to generate an embedding for

        Returns:
            List of floats representing the embedding vector

        Raises:
            ValueError: If content is empty
            Exception: If API request fails
        """
        if not content:
            raise ValueError("Content cannot be empty")

        # Ensure async client is initialized
        self._create_async_client()

        logger.info(f"Generating embedding for content: {len(content)} characters")

        try:
            # Use OpenAI's embeddings API (text-embedding-3-small by default)
            response = await self._async_client.embeddings.create(  # type: ignore
                model="text-embedding-3-small",
                input=content,
            )

            embedding = response.data[0].embedding
            logger.info(
                f"Successfully generated embedding: {len(embedding)} dimensions"
            )
            return embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {str(e)}")
            raise

    def estimate_token_count(self, text: str) -> int:
        """
        Estimate the number of tokens in a text string using tiktoken.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated number of tokens
        """
        if USE_MOCK_MODEL:
            # Mock mode: use simple word count estimation (roughly 1 token per 4 characters)
            return len(text) // 4

        import tiktoken

        try:
            encoding = tiktoken.encoding_for_model(self.model_class)
            tokens = encoding.encode(text)
            return len(tokens)
        except KeyError:
            # If model not recognized by tiktoken, fall back to character-based estimation
            logger.warning(
                f"Model '{self.model_class}' not recognized by tiktoken, using fallback estimation"
            )
            return len(text) // 4

    def get_max_context_tokens(self) -> int:
        """
        Get the maximum context token limit for the model.

        Returns:
            Maximum number of tokens the model can handle in its context
        """
        if USE_MOCK_MODEL:
            # Mock mode: return a safe default context size (same as gpt-4)
            return 8192

        # Known token limits for OpenAI models
        model_limits = {
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "gpt-4-turbo": 128000,
            "gpt-4-turbo-preview": 128000,
            "gpt-4": 8192,
            "gpt-4-32k": 32768,
            "gpt-3.5-turbo": 16385,
            "gpt-3.5-turbo-16k": 16385,
        }

        # Return known limit or default to 4096
        return model_limits.get(self.model_class, 4096)

    def _get_tool_definitions_for_thread(
        self, tools: Optional[list[AIToolBase]] = None
    ) -> list[FunctionToolParam]:
        if not tools or len(tools) == 0:
            return []
        return [FunctionToolParam(**t.get_tool_definition()) for t in tools]

    def initialize_thread(
        self,
        system_prompt: Optional[str] = None,
        initial_user_prompt: Optional[str] = None,
        tools: Optional[list[AIToolBase]] = None,
    ) -> str:
        self._create_client()

        thread_params = {
            "model": self.model_class,
            "instructions": system_prompt,
            "input": initial_user_prompt or "wait for next user conversation",
            "tools": self._get_tool_definitions_for_thread(tools=tools),
        }
        response = self._client.responses.create(**thread_params)  # type: ignore
        logger.info(f"Thread initialized with id: {response.id}")
        return response.id

    def handle_thread_request(
        self,
        messages: list[AIConversationMessageBase],
        tools: Optional[list[AIToolBase]] = None,
        previous_response_id: Optional[str] = None,
    ) -> AIConversationMessageBase:
        self._create_client()
        messages_serialized = []
        for message in messages:
            message_converted = self._convert_message_to_openai_message(message=message)
            if not message_converted:
                continue
            messages_serialized += [message_converted]
        response = self._client.responses.create(  # type: ignore
            model=self.model_class,
            input=messages_serialized,
            previous_response_id=previous_response_id,
            tools=self._get_tool_definitions_for_thread(tools=tools),
        )
        response_message = response.output_text
        tool_calls = []
        for item in response.output:
            if item.type == "function_call":
                if not isinstance(item, ResponseFunctionToolCall):
                    continue
                tool_name = item.name
                tool_params = item.arguments
                tool_call_id = item.call_id
                tool_calls += [
                    AIConversationToolCall(
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        tool_params=tool_params,
                    )
                ]
        result_message = OpenAIConversationMessage(
            role="assistant",
            content=response_message,
            tool_calls=tool_calls,
            id=response.id,
        )
        return result_message

    async def handle_thread_request_async(
        self,
        messages: list[AIConversationMessageBase],
        tools: Optional[list[AIToolBase]] = None,
        previous_response_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> AIConversationMessageBase:
        """
        Handle thread request asynchronously using OpenAI's responses API.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools
            previous_response_id: Optional ID of previous response for threading
            max_tokens: Optional maximum tokens for response

        Returns:
            AIConversationMessageBase with response content and tool calls
        """
        self._create_async_client()
        messages_serialized = []
        for message in messages:
            message_converted = self._convert_message_to_openai_message(message=message)
            if not message_converted:
                continue
            messages_serialized += [message_converted]

        # Build request parameters
        request_params = {
            "model": self.model_class,
            "input": messages_serialized,
            "previous_response_id": previous_response_id,
            "tools": self._get_tool_definitions_for_thread(tools=tools),
        }
        if max_tokens is not None:
            request_params["max_tokens"] = max_tokens

        response = await self._async_client.responses.create(**request_params)  # type: ignore
        response_message = response.output_text
        tool_calls = []
        for item in response.output:
            if item.type == "function_call":
                if not isinstance(item, ResponseFunctionToolCall):
                    continue
                tool_name = item.name
                tool_params = item.arguments
                tool_call_id = item.call_id
                tool_calls += [
                    AIConversationToolCall(
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        tool_params=tool_params,
                    )
                ]
        result_message = OpenAIConversationMessage(
            role="assistant",
            content=response_message,
            tool_calls=tool_calls,
            id=response.id,
        )
        return result_message

    def _create_client(self):
        if not self._client:
            if USE_MOCK_MODEL:
                from utilities.mock_model_client import MockOpenAI

                self._client = MockOpenAI(api_key=OPENAI_API_KEY)  # type: ignore
                logger.info("Using MockOpenAI client (USE_MOCK_MODEL=true)")
            else:
                self._client = OpenAI(api_key=OPENAI_API_KEY)

    def _create_async_client(self):
        if not self._async_client:
            if USE_MOCK_MODEL:
                from utilities.mock_model_client import MockOpenAI

                self._async_client = MockOpenAI(api_key=OPENAI_API_KEY, async_mode=True)  # type: ignore
                logger.info(
                    "Using MockOpenAI async client for embeddings (USE_MOCK_MODEL=true)"
                )
            else:
                self._async_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


if __name__ == "__main__":
    import asyncio

    async def interactive_mode():
        current_conversation = None
        model = OpenAIModel(model_class="gpt-4")
        print("Start OpenAI model in interactive mode (threaded conversation)!")
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
