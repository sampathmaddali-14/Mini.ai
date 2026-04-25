"""
Cognitive loop — entrypoint and sanity check.

Usage:
    python -m src.core.cognitive_loop               # sanity check: pings all services
    python -m src.core.cognitive_loop --seed        # seed fixture memories
    python -m src.core.cognitive_loop --fire <name> # manually fire a policy

For the real conversational agent loop, OpenClaw runs it. This module is for
operators and policy scripts that need to poke the stack directly.
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

from .memory_bridge import MemoryBridge


log = logging.getLogger("mini.cognitive_loop")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)


def sanity_check() -> int:
    """Ping each service. Return 0 if all healthy, non-zero otherwise."""
    results = {}

    mem = MemoryBridge()
    results["memos"] = mem.healthz()

    # OpenSpace + OpenClaw health checks — implemented once their endpoints
    # are defined. Skeleton for now:
    results["openspace"] = _http_ping(os.getenv("OPENSPACE_MCP_URL", "http://localhost:7080") + "/healthz")
    results["openclaw"] = _http_ping(os.getenv("OPENCLAW_URL", "http://localhost:7090") + "/healthz")

    ok = all(results.values())
    print(json.dumps({"healthy": ok, "services": results}, indent=2))
    mem.close()
    return 0 if ok else 1


def seed_fixtures() -> int:
    """Load a small set of deterministic memories for testing retrieval + policies."""
    mem = MemoryBridge()
    fixtures = [
        ("I prefer Docker Compose over Kubernetes for personal projects.", "semantic",
         ["Docker Compose", "Kubernetes"]),
        ("User is building Mini.ai, a brain-mimicking agentic architecture.", "semantic",
         ["Mini.ai"]),
        ("Stack: OpenClaw + MemOS + OpenSpace + Qdrant + Kuzu + Claude API.", "semantic",
         ["OpenClaw", "MemOS", "OpenSpace", "Qdrant", "Kuzu", "Claude"]),
        ("No copyleft dependencies — MIT and Apache 2.0 only.", "semantic", []),
        ("User asked about deployment topology on Friday afternoon.", "episodic", []),
        ("Heartbeat schedule: 30m reflection, hourly rewire, daily consolidation, weekly pruning.",
         "semantic", []),
    ]
    n = 0
    for content, tier, entities in fixtures:
        try:
            m = mem.add(content=content, tier=tier, entities=entities, source="fixture")
            log.info(f"seeded id={m.id} tier={tier}")
            n += 1
        except Exception as e:
            log.error(f"seed failed: {e}")
    mem.close()
    print(json.dumps({"seeded": n}, indent=2))
    return 0


def fire_policy(name: str) -> int:
    """Manually invoke a cognitive policy (for debugging)."""
    valid = {"curation", "rewire", "reflection", "consolidation", "pruning", "unlearn"}
    if name not in valid:
        print(f"Unknown policy: {name}. Valid: {sorted(valid)}", file=sys.stderr)
        return 2
    # Invoke via OpenSpace MCP. Stubbed here — wire the actual MCP call when
    # OpenSpace is up locally.
    print(json.dumps({
        "fired": name,
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": "TODO: wire OpenSpace MCP invocation",
    }, indent=2))
    return 0


def _http_ping(url: str) -> bool:
    import httpx
    try:
        r = httpx.get(url, timeout=2)
        return r.status_code < 500
    except Exception:
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Mini.ai operator entrypoint")
    p.add_argument("--seed", action="store_true", help="Seed fixture memories")
    p.add_argument("--fire", metavar="POLICY", help="Manually fire a cognitive policy")
    args = p.parse_args()

    if args.seed:
        return seed_fixtures()
    if args.fire:
        return fire_policy(args.fire)
    return sanity_check()


if __name__ == "__main__":
    raise SystemExit(main())
