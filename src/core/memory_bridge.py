"""
Thin HTTP client for MemOS. The official plugin handles the OpenClaw <-> MemOS
path. This bridge is for our own Python code (policies, inspection, scripts).

Keep this intentionally minimal. If MemOS's API changes, only this file does.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import os
import httpx


MEMOS_URL = os.getenv("MEMOS_URL", "http://localhost:7070")
TIMEOUT = float(os.getenv("MEMOS_TIMEOUT", "10"))


@dataclass
class Memory:
    id: str
    content: str
    tier: str                 # episodic | semantic | long_term
    timestamp: datetime
    source: Optional[str] = None
    entities: Optional[list[str]] = None
    decay_score: Optional[float] = None
    status: Optional[str] = None   # active | superseded | tombstone


class MemoryBridge:
    def __init__(self, base_url: str = MEMOS_URL):
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(timeout=TIMEOUT)

    # ---- writes ----

    def add(
        self,
        content: str,
        tier: str = "episodic",
        source: Optional[str] = None,
        entities: Optional[list[str]] = None,
        user_override: bool = False,
    ) -> Memory:
        payload = {
            "content": content,
            "tier": tier,
            "source": source,
            "entities": entities or [],
            "user_override": user_override,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        r = self._client.post(f"{self._base}/memories", json=payload)
        r.raise_for_status()
        return _parse_memory(r.json())

    def update_status(self, memory_id: str, status: str) -> None:
        r = self._client.patch(
            f"{self._base}/memories/{memory_id}",
            json={"status": status},
        )
        r.raise_for_status()

    def delete(self, memory_id: str, reason: str = "unlearn") -> None:
        r = self._client.delete(
            f"{self._base}/memories/{memory_id}",
            params={"reason": reason},
        )
        r.raise_for_status()

    # ---- reads ----

    def search(
        self,
        query: str,
        tier: Optional[str] = None,
        top_k: int = 8,
        hide_superseded: bool = True,
    ) -> list[Memory]:
        params = {"q": query, "top_k": top_k, "hide_superseded": hide_superseded}
        if tier:
            params["tier"] = tier
        r = self._client.get(f"{self._base}/memories/search", params=params)
        r.raise_for_status()
        return [_parse_memory(m) for m in r.json().get("results", [])]

    def get(self, memory_id: str) -> Memory:
        r = self._client.get(f"{self._base}/memories/{memory_id}")
        r.raise_for_status()
        return _parse_memory(r.json())

    def recent(self, tier: str = "episodic", limit: int = 20) -> list[Memory]:
        r = self._client.get(
            f"{self._base}/memories",
            params={"tier": tier, "limit": limit, "order": "desc"},
        )
        r.raise_for_status()
        return [_parse_memory(m) for m in r.json().get("results", [])]

    def count(self, tier: Optional[str] = None, since: Optional[datetime] = None) -> int:
        params = {}
        if tier:
            params["tier"] = tier
        if since:
            params["since"] = since.isoformat()
        r = self._client.get(f"{self._base}/memories/count", params=params)
        r.raise_for_status()
        return int(r.json().get("count", 0))

    # ---- health ----

    def healthz(self) -> bool:
        try:
            r = self._client.get(f"{self._base}/healthz", timeout=2)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def close(self) -> None:
        self._client.close()


def _parse_memory(d: dict) -> Memory:
    ts = d.get("timestamp")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return Memory(
        id=d["id"],
        content=d["content"],
        tier=d.get("tier", "episodic"),
        timestamp=ts or datetime.now(timezone.utc),
        source=d.get("source"),
        entities=d.get("entities"),
        decay_score=d.get("decay_score"),
        status=d.get("status"),
    )
