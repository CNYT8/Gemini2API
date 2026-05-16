"""Structured log store with circular buffer, filtering, and pagination."""

import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from threading import Lock
from typing import Optional


@dataclass
class LogRecord:
    id: str
    request_id: str
    direction: str
    ts: str
    method: str
    path: str
    model: Optional[str] = None
    provider: Optional[str] = None
    status: Optional[int] = None
    latency_ms: Optional[float] = None
    stream: Optional[bool] = None
    error: Optional[str] = None
    tags: list = field(default_factory=list)
    request: Optional[dict] = None
    response: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def matches_search(self, query: str) -> bool:
        q = query.lower()
        searchable = [
            self.path,
            self.method,
            self.model or "",
            self.error or "",
            str(self.status) if self.status else "",
        ]
        return any(q in s.lower() for s in searchable)


@dataclass
class LogState:
    enabled: bool = True
    paused: bool = False


class LogStore:
    def __init__(self, capacity: int = 2000):
        self._buffer: deque[LogRecord] = deque(maxlen=capacity)
        self._lock = Lock()
        self._state = LogState()
        self._id_index: dict[str, LogRecord] = {}

    @property
    def state(self) -> LogState:
        return self._state

    def add(self, record: LogRecord) -> None:
        if not self._state.enabled or self._state.paused:
            return
        with self._lock:
            if len(self._buffer) == self._buffer.maxlen:
                evicted = self._buffer[0]
                self._id_index.pop(evicted.id, None)
            self._buffer.append(record)
            self._id_index[record.id] = record

    def query(
        self,
        limit: int = 50,
        offset: int = 0,
        direction: str = "all",
        search: str = "",
    ) -> dict:
        with self._lock:
            records = list(reversed(self._buffer))

        if direction != "all":
            records = [r for r in records if r.direction == direction]

        if search:
            records = [r for r in records if r.matches_search(search)]

        total = len(records)
        page = records[offset : offset + limit]
        return {
            "records": [r.to_dict() for r in page],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get(self, record_id: str) -> Optional[dict]:
        with self._lock:
            record = self._id_index.get(record_id)
        if record:
            return record.to_dict()
        return None

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._id_index.clear()

    def get_state(self) -> dict:
        return {"enabled": self._state.enabled, "paused": self._state.paused}

    def set_state(self, enabled: Optional[bool] = None, paused: Optional[bool] = None) -> dict:
        if enabled is not None:
            self._state.enabled = enabled
        if paused is not None:
            self._state.paused = paused
        return self.get_state()


def create_log_record(
    method: str,
    path: str,
    direction: str = "ingress",
    model: Optional[str] = None,
    status: Optional[int] = None,
    latency_ms: Optional[float] = None,
    stream: Optional[bool] = None,
    error: Optional[str] = None,
    request_body: Optional[dict] = None,
    response_body: Optional[dict] = None,
) -> LogRecord:
    now = datetime.now(timezone.utc).isoformat()
    return LogRecord(
        id=uuid.uuid4().hex[:12],
        request_id=uuid.uuid4().hex[:8],
        direction=direction,
        ts=now,
        method=method,
        path=path,
        model=model,
        provider="gemini",
        status=status,
        latency_ms=round(latency_ms, 1) if latency_ms is not None else None,
        stream=stream,
        error=error,
        request=request_body,
        response=response_body,
    )
