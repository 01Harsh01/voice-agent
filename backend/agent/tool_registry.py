"""
Tool Registry module.
Provides abstract BaseTool and ToolRegistry that generates OpenAI-compatible tool specifications
for LLM function calling and dispatches executions.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import json
from backend.logging import logger


class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        pass

    def to_openai_tool(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema
            }
        }


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        return [tool.to_openai_tool() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: Any) -> Dict[str, Any]:
        tool = self.get(name)
        if not tool:
            logger.error(f"Tool not found: {name}")
            return {
                "error": f"Tool '{name}' is not recognized. Available tools: {list(self._tools.keys())}"
            }

        # Parse arguments if string
        if isinstance(arguments, str):
            try:
                args_dict = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse arguments JSON for tool {name}: {e}")
                return {"error": f"Invalid JSON arguments for tool '{name}': {str(e)}"}
        elif isinstance(arguments, dict):
            args_dict = arguments
        else:
            args_dict = {}

        try:
            logger.info(f"Executing tool {name}", args=args_dict)
            result = await tool.execute(**args_dict)
            return result
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            return {
                "error": f"Failed executing {name}: {str(e)}"
            }
