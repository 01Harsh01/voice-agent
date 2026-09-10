"""
Request Manager module.
Manages request lifecycles, states, unique request IDs, cancellation tokens,
and ensures strict stale-result rejection during barge-in.
"""
import asyncio
from enum import Enum
import time
import uuid
from typing import Dict, Optional, Set
from backend.logging import logger


class RequestState(str, Enum):
    CREATED = "CREATED"
    TRANSCRIBING = "TRANSCRIBING"
    REASONING = "REASONING"
    TOOL_CALLING = "TOOL_CALLING"
    SYNTHESIZING = "SYNTHESIZING"
    SPEAKING = "SPEAKING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class RequestHandle:
    def __init__(self, request_id: str, conversation_id: str):
        self.request_id = request_id
        self.conversation_id = conversation_id
        self.state = RequestState.CREATED
        self.created_at = time.time()
        self.completed_at: Optional[float] = None
        self._cancel_event = asyncio.Event()
        self.async_tasks: Set[asyncio.Task] = set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set() or self.state == RequestState.CANCELLED

    def transition_to(self, new_state: RequestState) -> None:
        if self.is_cancelled and new_state != RequestState.CANCELLED:
            logger.warning(
                f"Ignoring transition to {new_state} for cancelled request {self.request_id}"
            )
            return
        self.state = new_state
        logger.debug(f"Request {self.request_id} transitioned to {new_state}")

    def cancel(self) -> None:
        self.state = RequestState.CANCELLED
        self._cancel_event.set()
        self.completed_at = time.time()
        for task in list(self.async_tasks):
            if not task.done():
                task.cancel()
        logger.info(f"Request {self.request_id} cancelled")

    def register_task(self, task: asyncio.Task) -> None:
        self.async_tasks.add(task)
        task.add_done_callback(lambda t: self.async_tasks.discard(t))


class RequestManager:
    def __init__(self):
        self._active_requests: Dict[str, RequestHandle] = {}
        self._latest_request_by_convo: Dict[str, str] = {}

    def create_request(self, conversation_id: str) -> RequestHandle:
        # If there is already an active request for this conversation, cancel it (barge-in)
        if conversation_id in self._latest_request_by_convo:
            old_req_id = self._latest_request_by_convo[conversation_id]
            self.cancel_request(old_req_id)

        req_id = f"req_{uuid.uuid4().hex[:8]}"
        handle = RequestHandle(request_id=req_id, conversation_id=conversation_id)
        self._active_requests[req_id] = handle
        self._latest_request_by_convo[conversation_id] = req_id
        logger.info(f"Created request {req_id} for conversation {conversation_id}")
        return handle

    def get_request(self, request_id: str) -> Optional[RequestHandle]:
        return self._active_requests.get(request_id)

    def is_stale(self, request_id: str, conversation_id: str) -> bool:
        handle = self.get_request(request_id)
        if not handle or handle.is_cancelled:
            return True
        latest_id = self._latest_request_by_convo.get(conversation_id)
        return latest_id != request_id

    def cancel_request(self, request_id: str) -> None:
        handle = self.get_request(request_id)
        if handle and not handle.is_cancelled:
            handle.cancel()

    def complete_request(self, request_id: str) -> None:
        handle = self.get_request(request_id)
        if handle and not handle.is_cancelled:
            handle.transition_to(RequestState.COMPLETED)
            handle.completed_at = time.time()
