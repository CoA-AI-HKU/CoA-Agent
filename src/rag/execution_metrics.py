from __future__ import annotations

import threading
from typing import Any


_lock = threading.Lock()
_total_messages = 0
_retrieved_messages = 0
_skipped_retrieval = 0
_score_total = 0.0
_chunk_total = 0


def record_retrieval(*, enabled: bool, scores: list[float], chunk_count: int) -> None:
    global _total_messages, _retrieved_messages, _skipped_retrieval, _score_total, _chunk_total
    with _lock:
        _total_messages += 1
        if enabled:
            _retrieved_messages += 1
            _score_total += sum(scores) / len(scores) if scores else 0.0
            _chunk_total += chunk_count
        else:
            _skipped_retrieval += 1


def retrieval_metrics_snapshot() -> dict[str, Any]:
    with _lock:
        retrieved = _retrieved_messages
        return {
            "total_messages": _total_messages,
            "retrieved_messages": retrieved,
            "skipped_retrieval": _skipped_retrieval,
            "average_retrieval_score": _score_total / retrieved if retrieved else 0.0,
            "average_retrieved_chunk_count": _chunk_total / retrieved if retrieved else 0.0,
        }
