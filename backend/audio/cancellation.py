"""
Cancellation and Barge-in management module.
Coordinates instantaneous abort of ongoing LLM reasoning, external tool execution,
and active Rime audio streaming when user speech is detected.
"""
from typing import Callable, Optional
from backend.logging import logger
from backend.agent.request_manager import RequestHandle, RequestManager


class BargeInManager:
    def __init__(self, request_manager: RequestManager):
        self.request_manager = request_manager

    def handle_user_interruption(
        self,
        conversation_id: str,
        current_request_id: Optional[str] = None
    ) -> None:
        """
        Executes immediate barge-in:
        Cancels active request tasks, flushes pending queues, and rejects stale operations.
        """
        if current_request_id:
            logger.info(f"Barge-in triggered explicitly for request: {current_request_id}")
            self.request_manager.cancel_request(current_request_id)
        else:
            # Cancel whatever request is currently active for this conversation
            latest_req_id = self.request_manager._latest_request_by_convo.get(conversation_id)
            if latest_req_id:
                logger.info(f"Barge-in triggered for active request: {latest_req_id}")
                self.request_manager.cancel_request(latest_req_id)
