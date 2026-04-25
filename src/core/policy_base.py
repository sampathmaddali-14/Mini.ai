"""
Base types and contract shared by all six cognitive policies.

Every policy:
  1. Inherits from CognitivePolicy
  2. Implements run(ctx) -> PolicyResult
  3. Emits a structured log entry via ctx.log(...)
  4. Is idempotent — rerunning with the same inputs should not cause drift

The PolicyContext bundles everything a policy needs: memory bridge, LLM client,
config, logger. This keeps policy code small and testable.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional
import json
import logging
import os
import uuid

from .memory_bridge import MemoryBridge


# ---- Result type ----

@dataclass
class PolicyResult:
    policy: str
    ok: bool
    summary: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None

    def to_json(self) -> str:
        d = asdict(self)
        d["started_at"] = self.started_at.isoformat()
        d["ended_at"] = self.ended_at.isoformat() if self.ended_at else None
        return json.dumps(d)


# ---- Context ----

class PolicyContext:
    """Everything a policy needs at runtime. Swappable components live here."""

    def __init__(
        self,
        memory: Optional[MemoryBridge] = None,
        llm: Optional["LLMClient"] = None,
        dry_run: bool = False,
    ):
        self.memory = memory or MemoryBridge()
        self.llm = llm or LLMClient()
        self.dry_run = dry_run
        self.logger = logging.getLogger("mini.policy")
        self.trace_id = uuid.uuid4().hex[:12]

    def log(self, policy: str, **fields: Any) -> None:
        """Emit a structured log line for a policy firing."""
        entry = {
            "policy": policy,
            "trace_id": self.trace_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "dry_run": self.dry_run,
            **fields,
        }
        self.logger.info(json.dumps(entry))


# ---- LLM client (thin wrapper over Anthropic API) ----

class LLMClient:
    """
    Minimal client. Policies call ask() with a prompt and optional JSON schema.
    Swap the implementation without changing policies.
    """

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.getenv("MEMOS_DEFAULT_MODEL", "claude-opus-4-7")
        self._api_key = os.getenv("ANTHROPIC_API_KEY", "")

    def ask(self, prompt: str, *, max_tokens: int = 1024, system: Optional[str] = None,
            expect_json: bool = False) -> str:
        """Send a prompt, return text. If expect_json, strip code fences."""
        import httpx
        if not self._api_key:
            # Offline / test mode — return a safe stub.
            return "[]" if expect_json else ""
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                json=body, headers=headers, timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            text = "".join(
                b.get("text", "") for b in data.get("content", [])
                if b.get("type") == "text"
            )
            if expect_json:
                text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return text
        except Exception as e:
            logging.getLogger("mini.llm").error(f"LLM call failed: {e}")
            return "[]" if expect_json else ""


# ---- Policy base class ----

class CognitivePolicy(ABC):
    name: str = "unnamed"

    @abstractmethod
    def run(self, ctx: PolicyContext, **kwargs: Any) -> PolicyResult:
        """Execute the policy. Must be idempotent."""

    def _result(self, ok: bool = True, **summary: Any) -> PolicyResult:
        r = PolicyResult(policy=self.name, ok=ok, summary=dict(summary))
        r.ended_at = datetime.now(timezone.utc)
        return r
