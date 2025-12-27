from __future__ import annotations

import traceback
from abc import abstractmethod
from string import Template
from typing import Optional

from pydantic import BaseModel, ConfigDict

from models.base_model import AIConversationBase, AIModelBase
from tools.base_tool import AIToolBase
from utilities import logger


class AIAgentToolResult(BaseModel):
    tool: str

    display: str

    params: str

    result: str


class AIAgentBase(BaseModel):
    """Agent is an entity that contains the context of a conversation to solve a particular task using a specific model."""

    model: AIModelBase
    """Model that the agent should use."""

    instruction: Template
    """Define the instruction (system prompt) to the agent about how to complete the task"""

    instruction_arguments: Optional[dict[str, str]] = None
    """Optionally provide instruction arguments"""

    tools: list[AIToolBase] = []
    """Defines the list of tools available to this agent."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    def get_instruction(self) -> str:
        if not self.instruction_arguments:
            self.instruction_arguments = {}
        return self.instruction.safe_substitute(**self.instruction_arguments)

    def _ensure_tool_overrides(self):
        """Ensure all tools have the override_run methods set for result saving."""
        for tool in self.tools:
            if tool.override_run is None:
                tool.override_run = self._tool_override_run_and_save_result
            if tool.override_run_async is None:
                tool.override_run_async = self._tool_override_run_and_save_result_async

    def run_agent_conversation(
        self,
        user_prompt: str,
        current_conversation: Optional[AIConversationBase] = None,
    ) -> AIConversationBase:
        # Ensure tools have overrides set for result saving
        self._ensure_tool_overrides()

        if not current_conversation:
            current_conversation = self.model.create_conversation(
                system_prompt=self.get_instruction(), tools=self.tools
            )
        current_conversation.run_chat_completion(user_prompt=user_prompt)
        return current_conversation

    async def run_agent_conversation_async(
        self,
        user_prompt: str,
        current_conversation: Optional[AIConversationBase] = None,
    ) -> AIConversationBase:
        """Async version of run_agent_conversation that uses async chat completion."""
        # Ensure tools have overrides set for result saving
        self._ensure_tool_overrides()

        if not current_conversation:
            current_conversation = self.model.create_conversation(
                system_prompt=self.get_instruction(), tools=self.tools
            )
        await current_conversation.run_chat_completion_async(user_prompt=user_prompt)
        return current_conversation

    def add_tools(self, tools: list[AIToolBase]):
        for existing_tool in self.tools:
            skip = False
            for tool in tools:
                if tool.name == existing_tool.name:
                    skip = True
                    break
            if skip:
                continue
            tools += [existing_tool]
        self.tools = tools
        self._ensure_tool_overrides()

    def _tool_override_run_and_save_result(self, tool: AIToolBase, params: str) -> str:
        result = tool.run_tool(params=params, skip_override=True)
        try:
            result_serialized = None
            if result:
                result_serialized = AIAgentToolResult(
                    tool=tool.name,
                    display=tool.get_tool_display_name(params=params),
                    params=params,
                    result=result,
                )
            if result_serialized:
                self._save_tool_run_result(result=result_serialized)
        except Exception as e:
            logger.error(f"{str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                logger.error(f"  {tb}")
        return result

    async def _tool_override_run_and_save_result_async(
        self, tool: AIToolBase, params: str
    ) -> str:
        """Async version of _tool_override_run_and_save_result for async tool execution."""
        result = await tool.run_tool_async(params=params, skip_override=True)
        try:
            result_serialized = None
            if result:
                result_serialized = AIAgentToolResult(
                    tool=tool.name,
                    display=tool.get_tool_display_name(params=params),
                    params=params,
                    result=result,
                )
            if result_serialized:
                self._save_tool_run_result(result=result_serialized)
        except Exception as e:
            logger.error(f"{str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                logger.error(f"  {tb}")
        return result

    @abstractmethod
    def _save_tool_run_result(self, result: AIAgentToolResult):
        raise NotImplementedError

    @abstractmethod
    def hand_off_to_next_agent(self, agent: AIAgentBase):
        raise NotImplementedError

    def update_instructions(self, **kwargs):
        if not self.instruction_arguments:
            self.instruction_arguments = {}
        self.instruction_arguments.update(kwargs)

    def run_agent_interactive(self):
        current_conversation = None
        print(
            """
*******************************************************************************
*                    Agent interactive mode started!                          *
* Commands:                                                                   *
*   exit  - quit the interactive mode                                         *
*   info  - display agent instruction                                         *
*   new   - start a new conversation                                          *
*******************************************************************************
"""
        )
        while True:
            user_prompt = input("> ")
            if user_prompt.strip().lower() == "exit":
                return
            elif user_prompt.strip().lower() == "new":
                current_conversation = None
                print(">> Start New Conversation <<")
                continue
            elif user_prompt.strip().lower() == "info":
                print(self.get_instruction())
                continue
            current_conversation = self.run_agent_conversation(
                user_prompt=user_prompt, current_conversation=current_conversation
            )
            print(current_conversation.last_model_response)
