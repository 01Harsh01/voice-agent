"""
Context Manager for maintaining conversational turns and session state.
Adheres to strict anti-contamination policy: previous turns are reference history,
never default or cached answers.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Turn(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str
    request_id: Optional[str] = None
    timestamp: Optional[float] = None
    tool_calls_summary: Optional[List[str]] = None


class ConversationContext:
    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.turns: List[Turn] = []

    def add_user_turn(self, content: str, request_id: str, timestamp: Optional[float] = None) -> None:
        self.turns.append(Turn(
            role="user",
            content=content,
            request_id=request_id,
            timestamp=timestamp
        ))

    def add_assistant_turn(
        self,
        content: str,
        request_id: str,
        tool_calls_summary: Optional[List[str]] = None,
        timestamp: Optional[float] = None
    ) -> None:
        self.turns.append(Turn(
            role="assistant",
            content=content,
            request_id=request_id,
            tool_calls_summary=tool_calls_summary,
            timestamp=timestamp
        ))

    def to_messages(self, system_prompt: str, max_turns: int = 10) -> List[Dict[str, Any]]:
        """
        Builds the message list for the LLM.
        Includes system prompt, followed by the actual recent turns.
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]

        recent = self.turns[-max_turns:] if len(self.turns) > max_turns else self.turns
        for turn in recent:
            messages.append({
                "role": turn.role,
                "content": turn.content
            })

        return messages

    def clear(self) -> None:
        self.turns.clear()
