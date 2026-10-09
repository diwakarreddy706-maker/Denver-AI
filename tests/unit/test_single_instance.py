"""Unit tests for Denver Single-Instance Guard."""

from __future__ import annotations

import uuid
from denver.utils.single_instance import SingleInstanceGuard


def test_single_instance_guard_lifecycle() -> None:
    unique_name = f"Local\\Denver_Test_{uuid.uuid4().hex}"

    guard1 = SingleInstanceGuard(mutex_name=unique_name)
    guard2 = SingleInstanceGuard(mutex_name=unique_name)

    try:
        # First guard acquires successfully
        acquired1 = guard1.acquire()
        assert acquired1 is True

        # Second guard must fail to acquire while first is active
        acquired2 = guard2.acquire()
        assert acquired2 is False
    finally:
        guard1.release()
        guard2.release()

    # After release, guard can acquire again
    guard3 = SingleInstanceGuard(mutex_name=unique_name)
    try:
        assert guard3.acquire() is True
    finally:
        guard3.release()
