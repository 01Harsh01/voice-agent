"""
Tests for Request Isolation and Barge-in Cancellation.
Ensures that user interruptions cancel prior tasks and stale callbacks are rejected.
"""
import asyncio
import pytest
from backend.agent.request_manager import RequestManager, RequestState


@pytest.mark.asyncio
async def test_request_isolation_and_barge_in_cancellation():
    rm = RequestManager()
    convo_id = "test_convo_1"

    # Turn 1 created
    req1 = rm.create_request(convo_id)
    assert req1.state == RequestState.CREATED
    assert not req1.is_cancelled

    # Simulate an active background task
    async def long_task():
        await asyncio.sleep(10)

    task1 = asyncio.create_task(long_task())
    req1.register_task(task1)

    # User interrupts / starts Turn 2
    req2 = rm.create_request(convo_id)

    # Verify req1 is immediately cancelled
    assert req1.is_cancelled
    assert req1.state == RequestState.CANCELLED
    assert rm.is_stale(req1.request_id, convo_id) is True

    # Verify req2 is the new active request
    assert not req2.is_cancelled
    assert rm.is_stale(req2.request_id, convo_id) is False

    # Verify background task1 was cancelled
    await asyncio.sleep(0.05)
    assert task1.cancelled() or task1.done()
