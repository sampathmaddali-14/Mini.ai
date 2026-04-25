"""
⚠️ STALE — DO NOT USE AS-IS (2026-04-25 Architecture L pivot)

Reads memories via MemoryBridge (HTTP client to a service that doesn't exist
in Arch L). To be rewritten in Sprint 0 (story S010) as a direct reader of the
MemOS Local plugin's SQLite database.

Original docstring follows.
---
Memory inspector — simple CLI for browsing the agent's memory.

Usage:
    python -m src.core.inspect memories --last 20
    python -m src.core.inspect memories --tier semantic --limit 50
    python -m src.core.inspect search "Docker Compose"
    python -m src.core.inspect health
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime

from .memory_bridge import MemoryBridge


def _serialize(m) -> dict:
    return {
        "id": m.id,
        "tier": m.tier,
        "ts": m.timestamp.isoformat() if isinstance(m.timestamp, datetime) else m.timestamp,
        "source": m.source,
        "status": m.status,
        "decay": m.decay_score,
        "content": (m.content[:140] + "…") if len(m.content) > 140 else m.content,
    }


def cmd_memories(args) -> int:
    mem = MemoryBridge()
    rows = mem.recent(tier=args.tier, limit=args.last or args.limit)
    print(json.dumps([_serialize(m) for m in rows], indent=2))
    mem.close()
    return 0


def cmd_search(args) -> int:
    mem = MemoryBridge()
    rows = mem.search(query=args.query, tier=args.tier, top_k=args.top_k)
    print(json.dumps([_serialize(m) for m in rows], indent=2))
    mem.close()
    return 0


def cmd_health(args) -> int:
    mem = MemoryBridge()
    ok = mem.healthz()
    mem.close()
    print(json.dumps({"memos_healthy": ok}, indent=2))
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(prog="inspect", description="Mini.ai memory inspector")
    sub = p.add_subparsers(dest="cmd", required=True)

    mp = sub.add_parser("memories", help="Dump recent memories")
    mp.add_argument("--last", type=int, default=None)
    mp.add_argument("--limit", type=int, default=20)
    mp.add_argument("--tier", default="episodic", choices=["episodic", "semantic", "long_term"])
    mp.set_defaults(func=cmd_memories)

    sp = sub.add_parser("search", help="Search memories")
    sp.add_argument("query")
    sp.add_argument("--tier", default=None)
    sp.add_argument("--top-k", type=int, default=8)
    sp.set_defaults(func=cmd_search)

    hp = sub.add_parser("health", help="Health check")
    hp.set_defaults(func=cmd_health)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
