"""
⚠️ STALE — DO NOT USE AS-IS (2026-04-25 Architecture L pivot)

Constructs a PolicyContext that wires a MemoryBridge HTTP client to a service
that doesn't exist in Arch L. The argparse/dispatch shape is still useful and
will be reused once policies invoke memory through the local plugin instead.

To be reworked in Sprint 0 (story S015).

Original docstring follows.
---
CLI for firing cognitive policies manually. Used by heartbeat or operators.

Usage:
    python -m src.core.run_policy curation --content "I prefer X"
    python -m src.core.run_policy rewire --mode sweep
    python -m src.core.run_policy consolidation
    python -m src.core.run_policy pruning --dry-run
    python -m src.core.run_policy reflection
    python -m src.core.run_policy unlearn --scope entity:Bob
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone

from ..core.policy_base import PolicyContext
from ..policies.salience import Candidate
from ..policies.curation import CurationPolicy
from ..policies.rewire import RewirePolicy
from ..policies.reflection import ReflectionPolicy
from ..policies.consolidation import ConsolidationPolicy
from ..policies.pruning import PruningPolicy
from ..policies.unlearn import UnlearnPolicy


def _ctx(dry: bool) -> PolicyContext:
    return PolicyContext(dry_run=dry)


def run_curation(args) -> int:
    ctx = _ctx(args.dry_run)
    cand = Candidate(
        content=args.content,
        timestamp=datetime.now(timezone.utc),
        entities=(args.entities or "").split(",") if args.entities else [],
        user_override=args.override,
    )
    res = CurationPolicy().run(ctx, candidate=cand, tier=args.tier)
    print(res.to_json())
    return 0 if res.ok else 1


def run_rewire(args) -> int:
    ctx = _ctx(args.dry_run)
    if args.mode == "resolve":
        if not (args.old and args.new):
            print("resolve mode requires --old and --new", file=sys.stderr)
            return 2
        res = RewirePolicy().run(ctx, mode="resolve",
                                 old_memory_id=args.old, new_memory_id=args.new,
                                 reason=args.reason or "contradiction")
    else:
        res = RewirePolicy().run(ctx, mode="sweep", window_hours=args.window_hours)
    print(res.to_json())
    return 0 if res.ok else 1


def run_reflection(args) -> int:
    ctx = _ctx(args.dry_run)
    res = ReflectionPolicy().run(ctx, window_minutes=args.window_minutes)
    print(res.to_json())
    return 0 if res.ok else 1


def run_consolidation(args) -> int:
    ctx = _ctx(args.dry_run)
    res = ConsolidationPolicy().run(ctx, date=args.date)
    print(res.to_json())
    return 0 if res.ok else 1


def run_pruning(args) -> int:
    ctx = _ctx(args.dry_run)
    res = PruningPolicy().run(ctx)
    print(res.to_json())
    return 0 if res.ok else 1


def run_unlearn(args) -> int:
    ctx = _ctx(args.dry_run)
    # Parse --scope as "type:value"
    try:
        stype, sval = args.scope.split(":", 1)
    except ValueError:
        print("scope must be formatted as type:value (e.g. entity:Bob)", file=sys.stderr)
        return 2
    res = UnlearnPolicy().run(ctx, scope={"type": stype, "value": sval},
                              confirmed=args.confirmed)
    print(res.to_json())
    return 0 if res.ok else 1


def main() -> int:
    p = argparse.ArgumentParser(prog="run_policy")
    p.add_argument("--dry-run", action="store_true")
    sub = p.add_subparsers(dest="policy", required=True)

    c = sub.add_parser("curation")
    c.add_argument("--content", required=True)
    c.add_argument("--entities", default="")
    c.add_argument("--tier", default="episodic", choices=["episodic", "semantic"])
    c.add_argument("--override", action="store_true")
    c.set_defaults(func=run_curation)

    r = sub.add_parser("rewire")
    r.add_argument("--mode", choices=["sweep", "resolve"], default="sweep")
    r.add_argument("--old")
    r.add_argument("--new")
    r.add_argument("--reason")
    r.add_argument("--window-hours", type=int, default=1)
    r.set_defaults(func=run_rewire)

    rf = sub.add_parser("reflection")
    rf.add_argument("--window-minutes", type=int, default=30)
    rf.set_defaults(func=run_reflection)

    con = sub.add_parser("consolidation")
    con.add_argument("--date", help="YYYY-MM-DD (default: yesterday)")
    con.set_defaults(func=run_consolidation)

    pr = sub.add_parser("pruning")
    pr.set_defaults(func=run_pruning)

    un = sub.add_parser("unlearn")
    un.add_argument("--scope", required=True,
                    help="type:value e.g. entity:Bob, memory_id:mem_123, topic:Acme")
    un.add_argument("--confirmed", action="store_true")
    un.set_defaults(func=run_unlearn)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
