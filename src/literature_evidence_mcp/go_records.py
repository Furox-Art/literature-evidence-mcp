"""Opt-in persisted Go metadata cache and cross-process request-rate gate."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from filelock import FileLock

from literature_evidence_mcp.native import go_probe_sources


async def go_cached_papers(query: str, limit: int = 5, ttl_seconds: int = 3600) -> dict:
    """Gather limited, unverified provider metadata; return explicit rate-limit status.

    Cache is a local performance optimization, NOT authoritative evidence.
    """
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 500:
        raise ValueError("query must be 2-500 characters")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("limit must be 1-20")
    if type(ttl_seconds) is not int or not 0 <= ttl_seconds <= 86400:
        raise ValueError("TTL must be 0-86400 seconds")
    root = Path(os.environ.get("LITERATURE_EVIDENCE_CACHE_DIR", str(
        Path.home() / ".cache" / "literature-evidence-mcp")))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps([query, limit], ensure_ascii=False).encode()).hexdigest()
    cached = root / (key + ".json")
    lock = FileLock(str(root / "api-rate.lock"), timeout=5)
    with lock:
        if cached.exists():
            try:
                data = json.loads(cached.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeDecodeError):
                data = {}
            if (isinstance(data, dict) and time.time() - data.get("timestamp", 0) < ttl_seconds
                    and isinstance(data.get("payload"), dict)):
                return {**data["payload"], "cache_status": "LOCAL_UNVERIFIED_CACHE"}
        gate_file = root / "last-request.txt"
        try:
            last = float(gate_file.read_text()) if gate_file.exists() else 0.0
        except (OSError, ValueError):
            last = 0.0
        now = time.time()
        if now - last < 5:
            return {"status": "LOCAL_RATE_LIMITED", "retry_after_seconds": round(5 - (now - last), 3)}
        gate_file.write_text(str(now), encoding="ascii")
    # Running outside the lock avoids starving other process calls.
    result = await go_probe_sources(query, limit, mode="records")
    if result.get("status") == "PROVIDER_RECORDS_ONLY_UNVERIFIED" and ttl_seconds > 0:
        record = json.dumps({"timestamp": time.time(), "payload": result},
                            ensure_ascii=False)
        if len(record) <= 500_000:
            tmp = root / (key + ".tmp")
            with FileLock(str(root / "api-rate.lock"), timeout=5):
                tmp.write_text(record, encoding="utf-8")
                os.replace(tmp, cached)
    return {**result, "cache_status": "FRESH_UNVERIFIED_DATA"}
