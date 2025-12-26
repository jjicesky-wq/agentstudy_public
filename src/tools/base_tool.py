from __future__ import annotations

from abc import abstractmethod
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict


class AIToolBase(BaseModel):
    tool_type: str = "function"
    """The type of the tool"""

    name: str
    """The name of the tool"""

    description: str
    """The description of the tool"""

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    """The parameters of the tool"""

    strict: bool = True
    """Whether the tool's parameter must be strictly followed by the agent"""

    override_run: Optional[Callable[[AIToolBase, str], str]] = None
    """Optionally supply a function to run when the tool is called by the agent. Otherwise uses the run method of this tool"""

    override_run_async: Optional[Callable[[AIToolBase, str], Any]] = None
    """Optionally supply an async function to run when the tool is called by the agent in async context. Otherwise uses the run_async method of this tool"""

    result_cache: dict[int, Any] = {}
    """Caches the tool output for reuse if necessary"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _hash_tool_args(self, params: str) -> int:
        """Create a unique hash based on input arguments."""
        return hash(f"{self.name} {params}")

    @abstractmethod
    def _run(self, params: str) -> str:
        """Actual logic of the tool (synchronous)"""
        raise NotImplementedError

    async def _run_async(self, params: str) -> str:
        """Actual logic of the tool (asynchronous). Override for true async tools."""
        # Default implementation: run sync version in executor
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run, params)

    def get_tool_definition(self) -> dict[str, Any]:
        """Get the description of the tool including its usage and parameters."""
        self.parameters["additionalProperties"] = False
        return {
            "type": self.tool_type,
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
                "strict": self.strict,
            },
        }

    def get_tool_display_name(self, params: str) -> str:
        return f"{self.name}({params})"

    def run_tool(self, params: str, skip_override: bool = False) -> str:
        """Execute the tool synchronously, optionally uses the cached result if specified."""
        use_cache = self.use_cached_result()
        key = self._hash_tool_args(params=params)
        if use_cache and key in self.result_cache.keys():
            return self.result_cache[key]

        if not skip_override and self.override_run:
            result = self.override_run(self, params)
        else:
            result = self._run(params=params)

        if use_cache:
            self.result_cache[key] = result
        return result

    async def run_tool_async(self, params: str, skip_override: bool = False) -> str:
        """Execute the tool asynchronously, optionally uses the cached result if specified."""
        use_cache = self.use_cached_result()
        key = self._hash_tool_args(params=params)
        if use_cache and key in self.result_cache.keys():
            return self.result_cache[key]

        if not skip_override:
            # Prefer async override if available
            if self.override_run_async:
                result = await self.override_run_async(self, params)
            elif self.override_run:
                # If only sync override_run is provided, run it in an executor
                import asyncio

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, self.override_run, self, params
                )
            else:
                result = await self._run_async(params=params)
        else:
            result = await self._run_async(params=params)

        if use_cache:
            self.result_cache[key] = result
        return result

    def use_cached_result(self) -> bool:
        """When calling the tool with the same parameter, can a cached result be used instead of calling the run method again."""
        return False
