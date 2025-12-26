from __future__ import annotations

from abc import abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from tools.base_tool import AIToolBase
from utilities import logger


class AIConversationToolCall(BaseModel):
    tool_call_id: str
    """Optionally supply the tool call id."""

    tool_name: str
    """Optionally supply the tool name that the model wants to call."""

    tool_params: str
    """Optionally supply the tool parameters."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")


class AIConversationMessageBase(BaseModel):
    """Message between the user and the model."""

    id: Optional[str] = None

    role: str
    """Role of the message, e.g. system, user, assistant, etc."""

    content: str
    """Content of the message or tool execution result."""

    tool_calls: Optional[list[AIConversationToolCall]] = None

    images: Optional[list[str]] = None
    """Optional list of image URLs or base64-encoded images to include with the message."""

    def serialize(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content}

# model create conversation
class AIConversationBase(BaseModel):
    """Contains the full context of a conversation between the user and the model."""

    model: AIModelBase
    """OpenAI model to use"""

    system_prompt: Optional[str] = None
    """Optionally supply the system prompt"""

    tools: Optional[list[AIToolBase]] = None
    """Optionally supply the set of tools"""

    initial_user_prompt: Optional[str] = None
    """Optionally supply the initial user prompt"""

    messages: list[AIConversationMessageBase] = []
    """Conversation between the user and the model"""

    last_model_response: Optional[str] = None
    """Last response from the model."""

    thread_mode: bool = False
    """Whether this is a thread"""

    previous_response_id: Optional[str] = None
    """Previous thread response id, only applicable for thread"""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.system_prompt:
            self.messages += [
                self._create_system_prompt_message(system_prompt=self.system_prompt)
            ]
        if self.initial_user_prompt:
            self.messages += [
                self._create_user_prompt_message(user_prompt=self.initial_user_prompt)
            ]
        if self.thread_mode:
            self._initialize_thread()

    def _initialize_thread(self):
        self.previous_response_id = self.model.initialize_thread(
            system_prompt=self.system_prompt,
            initial_user_prompt=self.initial_user_prompt,
            tools=self.tools,
        )

    def _create_system_prompt_message(
        self, system_prompt: str
    ) -> AIConversationMessageBase:
        return AIConversationMessageBase(role="system", content=system_prompt)

    def _create_user_prompt_message(
        self, user_prompt: str, images: Optional[list[str]] = None
    ) -> AIConversationMessageBase:
        return AIConversationMessageBase(
            role="user", content=user_prompt, images=images
        )

    @abstractmethod
    def _create_tool_result_message(
        self, tool_call_id: str, tool_name: str, tool_params: str, tool_result: str
    ) -> AIConversationMessageBase:
        raise NotImplementedError

    def _call_tool(self, tool_call_id: str, tool_name: str, params: str) -> str:
        logger.info(
            f"Model {self.model.model_class} called '{tool_name}' with parameters '{params}', tool call id: {tool_call_id}"
        )
        if not self.tools:
            logger.error(f"Model {self.model.model_class} does not have any tool")
            return "Error: the tool you tried to use does not exist!"
        for tool in self.tools:
            if tool.name != tool_name:
                continue
            # Call the tool's run method with the parameters given by the model.
            # Any error means the model used a wrong parameter.
            try:
                return tool.run_tool(params=params)
            except Exception as e:
                logger.error(f"Model provided invalid parameter: {str(e)}")
                return f"Error: you provided invalid parameter! {str(e)}"

        # Agent picked a non-existing tool, flag this as an error
        logger.error(
            f"Model {self.model.model_class} used an non-existing tool '{tool_name}'"
        )
        return "Error: the tool you tried to use does not exist!"

    async def _call_tool_async(
        self, tool_call_id: str, tool_name: str, params: str
    ) -> str:
        logger.info(
            f"Model {self.model.model_class} called '{tool_name}' with parameters '{params}', tool call id: {tool_call_id}"
        )
        if not self.tools:
            logger.error(f"Model {self.model.model_class} does not have any tool")
            return "Error: the tool you tried to use does not exist!"
        for tool in self.tools:
            if tool.name != tool_name:
                continue
            # Call the tool's async run method with the parameters given by the model.
            # Any error means the model used a wrong parameter.
            try:
                return await tool.run_tool_async(params=params)
            except Exception as e:
                logger.error(f"Model provided invalid parameter: {str(e)}")
                return f"Error: you provided invalid parameter! {str(e)}"

        # Agent picked a non-existing tool, flag this as an error
        logger.error(
            f"Model {self.model.model_class} used an non-existing tool '{tool_name}'"
        )
        return "Error: the tool you tried to use does not exist!"

    def run_chat_completion(
        self, user_prompt: str, images: Optional[list[str]] = None
    ) -> str:
        """Run the conversation by submitting a user prompt and get the model's response (synchronous version)

        Args:
            user_prompt: User message text
            images: Optional list of image URLs or base64-encoded images
        """
        next_message = self._create_user_prompt_message(
            user_prompt=user_prompt, images=images
        )
        self.messages += [next_message]
        if self.thread_mode:
            response_message = self.model.handle_thread_request(
                messages=[next_message],
                previous_response_id=self.previous_response_id,
                tools=self.tools,
            )
        else:
            response_message = self.model.handle_chat_completion_request(
                messages=self.messages, tools=self.tools
            )
        self.previous_response_id = response_message.id
        # Repeatedly handle the tool calls from the model.
        while response_message.tool_calls:
            self.messages.append(response_message)
            tool_responses = []
            for tool_call in response_message.tool_calls:
                tool_result = self._call_tool(
                    tool_call_id=tool_call.tool_call_id,
                    tool_name=tool_call.tool_name,
                    params=tool_call.tool_params,
                )
                tool_message = self._create_tool_result_message(
                    tool_call_id=tool_call.tool_call_id,
                    tool_name=tool_call.tool_name,
                    tool_result=tool_result,
                    tool_params=tool_call.tool_params,
                )
                tool_responses.append(tool_message)
                self.messages.append(tool_message)
            if self.thread_mode:
                response_message = self.model.handle_thread_request(
                    messages=tool_responses,
                    previous_response_id=self.previous_response_id,
                    tools=self.tools,
                )
            else:
                response_message = self.model.handle_chat_completion_request(
                    messages=self.messages, tools=self.tools
                )
            self.previous_response_id = response_message.id
        self.messages.append(response_message)
        self.previous_response_id = response_message.id
        self.last_model_response = response_message.content
        return response_message.content

    async def run_chat_completion_async(
        self,
        user_prompt: str,
        max_tokens: Optional[int] = None,
        images: Optional[list[str]] = None,
    ) -> str:
        """Run the conversation by submitting a user prompt and get the model's response (async version)

        Args:
            user_prompt: User message text
            max_tokens: Optional maximum tokens in response
            images: Optional list of image URLs or base64-encoded images
        """
        next_message = self._create_user_prompt_message(
            user_prompt=user_prompt, images=images
        )
        self.messages += [next_message]

        if self.thread_mode:
            response_message = await self.model.handle_thread_request_async(
                messages=[next_message],
                previous_response_id=self.previous_response_id,
                max_tokens=max_tokens,
                tools=self.tools,
            )
        else:
            response_message = await self.model.handle_chat_completion_request_async(
                messages=self.messages, tools=self.tools, max_tokens=max_tokens
            )
        self.previous_response_id = response_message.id
        # Repeatedly handle the tool calls from the model.
        while response_message.tool_calls:
            self.messages.append(response_message)
            tool_responses = []
            for tool_call in response_message.tool_calls:
                tool_result = await self._call_tool_async(
                    tool_call_id=tool_call.tool_call_id,
                    tool_name=tool_call.tool_name,
                    params=tool_call.tool_params,
                )
                tool_message = self._create_tool_result_message(
                    tool_call_id=tool_call.tool_call_id,
                    tool_name=tool_call.tool_name,
                    tool_result=tool_result,
                    tool_params=tool_call.tool_params,
                )
                tool_responses.append(tool_message)
                self.messages.append(tool_message)
            if self.thread_mode:
                response_message = await self.model.handle_thread_request_async(
                    messages=tool_responses,
                    previous_response_id=self.previous_response_id,
                    max_tokens=max_tokens,
                    tools=self.tools,
                )
            else:
                response_message = (
                    await self.model.handle_chat_completion_request_async(
                        messages=self.messages, tools=self.tools
                    )
                )
                self.previous_response_id = response_message.id
        self.messages.append(response_message)
        self.previous_response_id = response_message.id
        self.last_model_response = response_message.content
        return response_message.content

    @abstractmethod
    def generate_image(self, prompt: str) -> bytes:
        """
        Generate an image from a text prompt (synchronous version).

        Args:
            prompt: Text description of the image to generate

        Returns:
            Image bytes (e.g., PNG format)

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        raise NotImplementedError

    @abstractmethod
    async def generate_image_async(self, prompt: str) -> bytes:
        """
        Generate an image from a text prompt (async version).

        Args:
            prompt: Text description of the image to generate

        Returns:
            Image bytes (e.g., PNG format)

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        raise NotImplementedError


class AIModelBase(BaseModel):
    """Takes in user input and uses the specific model (like GPT or Claude) to generate a response."""

    model_class: str
    """Model class to use, e.g. gpt-5-mini"""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    @abstractmethod
    def create_conversation(
        self,
        system_prompt: Optional[str] = None,
        initial_user_prompt: Optional[str] = None,
        tools: Optional[list[AIToolBase]] = None,
        thread_mode: bool = False,
    ) -> AIConversationBase:
        raise NotImplementedError

    @abstractmethod
    def handle_chat_completion_request(
        self,
        messages: list[AIConversationMessageBase],
        tools: Optional[list[AIToolBase]] = None,
    ) -> AIConversationMessageBase:
        raise NotImplementedError

    @abstractmethod
    async def handle_chat_completion_request_async(
        self,
        messages: list[AIConversationMessageBase],
        tools: Optional[list[AIToolBase]] = None,
        max_tokens: Optional[int] = None,
    ) -> AIConversationMessageBase:
        raise NotImplementedError

    @abstractmethod
    def handle_image_request(
        self,
        prompt: str,
        size: Optional[str] = None,
        quality: Optional[str] = None,
        style: Optional[str] = None,
    ) -> bytes:
        """
        Handle image generation request (synchronous version).

        Args:
            prompt: Text description of the image to generate
            size: Optional image size (e.g., "1024x1024", "512x512")
            quality: Optional quality setting (e.g., "standard", "hd")
            style: Optional style setting (e.g., "natural", "vivid")

        Returns:
            Image bytes (typically PNG format)

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        raise NotImplementedError

    @abstractmethod
    async def handle_image_request_async(
        self,
        prompt: str,
        size: Optional[str] = None,
        quality: Optional[str] = None,
        style: Optional[str] = None,
    ) -> bytes:
        """
        Handle image generation request (async version).

        Args:
            prompt: Text description of the image to generate
            size: Optional image size (e.g., "1024x1024", "512x512")
            quality: Optional quality setting (e.g., "standard", "hd")
            style: Optional style setting (e.g., "natural", "vivid")

        Returns:
            Image bytes (typically PNG format)

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        raise NotImplementedError

    @abstractmethod
    async def generate_embedding(self, content: str) -> list[float]:
        """
        Generate an embedding vector from the given content.

        Args:
            content: The text content to generate an embedding for

        Returns:
            List of floats representing the embedding vector

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        raise NotImplementedError

    @abstractmethod
    def estimate_token_count(self, text: str) -> int:
        """
        Estimate the number of tokens in a text string.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated number of tokens

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        raise NotImplementedError

    @abstractmethod
    def get_max_context_tokens(self) -> int:
        """
        Get the maximum context token limit for the model.

        Returns:
            Maximum number of tokens the model can handle in its context

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        raise NotImplementedError

    @abstractmethod
    def initialize_thread(
        self,
        system_prompt: Optional[str] = None,
        initial_user_prompt: Optional[str] = None,
        tools: Optional[list[AIToolBase]] = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def handle_thread_request(
        self,
        messages: list[AIConversationMessageBase],
        tools: Optional[list[AIToolBase]] = None,
        previous_response_id: Optional[str] = None,
    ) -> AIConversationMessageBase:
        raise NotImplementedError

    @abstractmethod
    async def handle_thread_request_async(
        self,
        messages: list[AIConversationMessageBase],
        tools: Optional[list[AIToolBase]] = None,
        previous_response_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> AIConversationMessageBase:
        raise NotImplementedError
