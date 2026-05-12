"""EventStore 异常 · Track F · Week 2 · Claude-B"""
from __future__ import annotations


class EventStoreError(Exception):
    """EventStore 通用异常基类"""


class SessionNotFoundError(EventStoreError):
    """目标 session 不存在"""


class InvalidForkError(EventStoreError):
    """fork_session 入参不合法"""


class EventNotFoundError(EventStoreError):
    """指定的 event_id 不存在"""
