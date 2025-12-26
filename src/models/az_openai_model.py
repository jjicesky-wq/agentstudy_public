from __future__ import annotations

from typing import Optional

from openai import AsyncAzureOpenAI, AzureOpenAI

from env_vars import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    USE_MOCK_MODEL,
)
from models.openai_model import OpenAIConversation, OpenAIModel
from tools.base_tool import AIToolBase
from utilities import logger


class AzureOpenAIConversation(OpenAIConversation):
    """Azure OpenAI-specific conversation implementation (inherits from OpenAI)."""

    def generate_image(self, prompt: str) -> bytes:
        """
        Generate an image from a text prompt using Azure OpenAI's image generation.

        Note: Azure OpenAI DALL-E support varies by region. Check your deployment.

        Args:
            prompt: Text description of the image to generate

        Returns:
            Image bytes (PNG format)
        """
        return self.model.handle_image_request(prompt=prompt)

    async def generate_image_async(self, prompt: str) -> bytes:
        """
        Generate an image from a text prompt using Azure OpenAI's image generation (async).

        Args:
            prompt: Text description of the image to generate

        Returns:
            Image bytes (PNG format)
        """
        return await self.model.handle_image_request_async(prompt=prompt)


class AzureOpenAIModel(OpenAIModel):
    """
    Azure OpenAI model implementation.

    Inherits from OpenAIModel and overrides client creation to use Azure endpoints.
    All other functionality (chat completion, thread mode, tool calling, embeddings)
    is inherited from OpenAIModel.
    """

    # Azure-specific attributes
    endpoint: str = ""
    api_version: str = ""

    def __init__(self, **kwargs):
        # Validate required Azure parameters before calling super().__init__
        if not AZURE_OPENAI_API_KEY:
            raise ValueError(
                "AZURE_OPENAI_API_KEY does not exist in environment variable"
            )
        if not AZURE_OPENAI_ENDPOINT:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT does not exist in environment variable"
            )

        # Set deployment name (model_class in Azure terms is the deployment name)
        if "model_class" not in kwargs:
            kwargs["model_class"] = AZURE_OPENAI_DEPLOYMENT

        # Call parent init
        super().__init__(**kwargs)

        if not self.model_class:
            raise ValueError("AZURE_OPENAI_DEPLOYMENT is not specified")

        # Store Azure-specific settings
        self.endpoint = AZURE_OPENAI_ENDPOINT
        self.api_version = AZURE_OPENAI_API_VERSION

    def create_conversation(
        self,
        system_prompt: Optional[str] = None,
        initial_user_prompt: Optional[str] = None,
        tools: Optional[list[AIToolBase]] = None,
        thread_mode: bool = False,
    ) -> AzureOpenAIConversation:
        """Create Azure-specific conversation that inherits OpenAI functionality."""
        return AzureOpenAIConversation(
            model=self,
            system_prompt=system_prompt,
            initial_user_prompt=initial_user_prompt,
            tools=tools,
            thread_mode=thread_mode,
        )

    def _create_client(self):
        """Override to use Azure OpenAI client."""
        if not self._client:
            if USE_MOCK_MODEL:
                from utilities.mock_model_client import MockOpenAI

                # Mock client can be used for Azure too since API is compatible
                self._client = MockOpenAI(api_key=AZURE_OPENAI_API_KEY)  # type: ignore
                logger.info("Using MockOpenAI client for Azure (USE_MOCK_MODEL=true)")
            else:
                self._client = AzureOpenAI(
                    api_key=AZURE_OPENAI_API_KEY,
                    azure_endpoint=self.endpoint,
                    api_version=self.api_version,
                )

    def _create_async_client(self):
        """Override to use Azure OpenAI async client."""
        if not self._async_client:
            if USE_MOCK_MODEL:
                from utilities.mock_model_client import MockOpenAI

                self._async_client = MockOpenAI(api_key=AZURE_OPENAI_API_KEY, async_mode=True)  # type: ignore
                logger.info(
                    "Using MockOpenAI async client for Azure (USE_MOCK_MODEL=true)"
                )
            else:
                self._async_client = AsyncAzureOpenAI(
                    api_key=AZURE_OPENAI_API_KEY,
                    azure_endpoint=self.endpoint,
                    api_version=self.api_version,
                )

    def get_max_context_tokens(self) -> int:
        """
        Get the maximum context token limit for the model.

        Returns:
            Maximum number of tokens the model can handle in its context
        """
        if USE_MOCK_MODEL:
            return 8192

        # Infer from deployment name (Azure deployments often include model info)
        deployment_lower = self.model_class.lower()

        # GPT-4 variants
        if "gpt-4o" in deployment_lower:
            return 128000
        elif "gpt-4-turbo" in deployment_lower:
            return 128000
        elif "gpt-4-32k" in deployment_lower:
            return 32768
        elif "gpt-4" in deployment_lower:
            return 8192

        # GPT-3.5 variants
        if (
            "gpt-35-turbo-16k" in deployment_lower
            or "gpt-3.5-turbo-16k" in deployment_lower
        ):
            return 16385
        elif "gpt-35-turbo" in deployment_lower or "gpt-3.5-turbo" in deployment_lower:
            return 4096

        # Default to a conservative estimate
        logger.warning(
            f"Unknown Azure deployment '{self.model_class}', defaulting to 4096 tokens"
        )
        return 4096


if __name__ == "__main__":
    import asyncio

    async def interactive_mode():
        current_conversation = None
        model = AzureOpenAIModel(model_class="gpt-4")  # Your Azure deployment name
        print("Start Azure OpenAI model in interactive mode (threaded conversation)!")
        print(f"Using endpoint: {model.endpoint}")
        print(f"Using deployment: {model.model_class}")
        print(f"API version: {model.api_version}")
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
