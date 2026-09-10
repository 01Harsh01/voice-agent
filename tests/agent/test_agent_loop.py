"""
Tests for Agent Loop reasoning and multi-turn context.
"""
import pytest
from typing import Any, Dict, List, Optional, Union
from backend.agent.agent_loop import AgentLoop
from backend.agent.context import ConversationContext
from backend.agent.request_manager import RequestManager
from backend.agent.tool_registry import ToolRegistry
from backend.tools.datetime import CurrentDateTimeTool
from backend.llm.base import BaseLLMProvider, LLMResponse, ToolCall


class MockDirectLLM(BaseLLMProvider):
    @property
    def name(self) -> str:
        return "mock_direct"

    @property
    def model_name(self) -> str:
        return "mock_model"

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Union[str, Dict[str, Any]] = "auto",
        **kwargs
    ) -> LLMResponse:
        # Returns direct explanation without tool calling
        return LLMResponse(
            content="TCP is connection-oriented and reliable, whereas UDP is connectionless and faster.",
            tool_calls=None
        )


class MockToolCallingLLM(BaseLLMProvider):
    def __init__(self):
        self.call_count = 0

    @property
    def name(self) -> str:
        return "mock_tool_caller"

    @property
    def model_name(self) -> str:
        return "mock_model"

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Union[str, Dict[str, Any]] = "auto",
        **kwargs
    ) -> LLMResponse:
        self.call_count += 1
        # On first turn, emit a tool call for current_datetime
        if self.call_count == 1:
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(id="call_dt_1", name="current_datetime", arguments="{}")
                ]
            )
        # On second turn (after evaluating tool result), synthesize answer
        return LLMResponse(
            content="Today is Tuesday, September 8, 2026.",
            tool_calls=None
        )


@pytest.mark.asyncio
async def test_agent_loop_direct_synthesis_no_tools():
    registry = ToolRegistry()
    registry.register(CurrentDateTimeTool())

    llm = MockDirectLLM()
    agent = AgentLoop(llm=llm, tool_registry=registry)

    rm = RequestManager()
    req = rm.create_request("convo_test")
    context = ConversationContext("convo_test")

    traces = []
    def trace_cb(stage, data):
        traces.append(stage)

    answer = await agent.run(
        user_text="What is the difference between TCP and UDP?",
        context=context,
        request_handle=req,
        trace_callback=trace_cb
    )

    assert "TCP is connection-oriented" in answer
    assert "TOOL_CALL_START" not in traces
    assert "LLM_SYNTHESIS" in traces
    assert len(context.turns) == 2  # 1 user + 1 assistant turn


@pytest.mark.asyncio
async def test_agent_loop_tool_execution_and_synthesis():
    registry = ToolRegistry()
    registry.register(CurrentDateTimeTool())

    llm = MockToolCallingLLM()
    agent = AgentLoop(llm=llm, tool_registry=registry)

    rm = RequestManager()
    req = rm.create_request("convo_test_2")
    context = ConversationContext("convo_test_2")

    traces = []
    def trace_cb(stage, data):
        traces.append(stage)

    answer = await agent.run(
        user_text="What day of the week is it today?",
        context=context,
        request_handle=req,
        trace_callback=trace_cb
    )

    assert "TOOL_CALL_START" in traces
    assert "TOOL_CALL_END" in traces
    assert "LLM_SYNTHESIS" in traces
    assert "Today is Tuesday" in answer
