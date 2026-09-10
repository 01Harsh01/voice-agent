"""
Abstract LLM Provider interface.
Defines contracts for chat completions with native tool calling and streaming.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str  # JSON string of arguments


class LLMResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


class BaseLLMProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Union[str, Dict[str, Any]] = "auto",
        temperature: float = 0.7,
        max_tokens: int = 500,
        request_id: Optional[str] = None
    ) -> LLMResponse:
        """
        Sends messages and available tool definitions to the LLM.
        Returns structured LLMResponse with either final content or tool_calls.
        """
        pass
