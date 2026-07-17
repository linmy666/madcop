"""CLI: python -m madcop.meta_harness [run|status|promote|axes|suites]

Examples::

    python -m madcop.meta_harness status
    python -m madcop.meta_harness run --iterations 5 --suite full --proposer code_edit
    python -m madcop.meta_harness run --iterations 3 --promote
    python -m madcop.meta_harness axes
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MadCop Meta-Harness (task harness search)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show active harness + archive best")
    sub.add_parser("axes", help="List searchable knobs")
    sub.add_parser("suites", help="List eval suite names")

    p_run = sub.add_parser("run", help="Run outer search loop")
    p_run.add_argument("--iterations", type=int, default=5)
    p_run.add_argument("--seed", type=int, default=0)
    p_run.add_argument("--promote", action="store_true", help="Write best to active.json")
    p_run.add_argument("--live", action="store_true", help="Use live LLM (costs tokens)")
    p_run.add_argument(
        "--suite",
        default="smoke",
        help="Eval suite: smoke | full",
    )
    p_run.add_argument(
        "--proposer",
        default="local",
        help="Proposer: local | code_edit | mock",
    )

    p_prom = sub.add_parser("promote", help="Promote archive best to active")
    p_prom.add_argument("--id", default="", help="Candidate dir name; default=best")

    args = parser.parse_args(argv)

    if args.cmd == "axes":
        from madcop.meta_harness.task_harness import list_knob_axes
        print(json.dumps(list_knob_axes(), indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "suites":
        from madcop.meta_harness.suites import SUITE_NAMES
        print(json.dumps(list(SUITE_NAMES), indent=2))
        return 0

    if args.cmd == "status":
        from madcop.meta_harness.archive import HarnessArchive
        from madcop.meta_harness.task_harness import load_active_harness
        active = load_active_harness()
        arch = HarnessArchive()
        best = arch.best()
        cands = arch.list_candidates()
        print("active:", json.dumps(active.to_dict(), indent=2, ensure_ascii=False))
        print("archive_best:", json.dumps(best, indent=2, ensure_ascii=False) if best else None)
        print("archive_count:", len(cands))
        return 0

    if args.cmd == "run":
        from madcop.meta_harness.loop import MetaHarnessLoop
        loop = MetaHarnessLoop(
            seed=args.seed,
            promote_best=args.promote,
            proposer=args.proposer,
            suite=args.suite,
        )
        result = loop.run(iterations=args.iterations, live_llm=args.live)
        print(
            json.dumps(
                {
                    "iterations": result.iterations,
                    "best_pass_rate": result.best_pass_rate,
                    "best": result.best.to_dict(),
                    "history": result.history,
                    "promoted": args.promote,
                    "suite": args.suite,
                    "proposer": result.proposer,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.cmd == "promote":
        from madcop.meta_harness.archive import HarnessArchive
        from madcop.meta_harness.task_harness import (
            ChatTaskHarness,
            save_active_harness,
        )
        import json as _j

        arch = HarnessArchive()
        if args.id:
            score_path = arch.root / args.id / "score.json"
            if not score_path.exists():
                matches = [
                    p for p in arch.root.iterdir()
                    if p.is_dir() and p.name.startswith(args.id)
                ]
                if not matches:
                    print(f"candidate not found: {args.id}", file=sys.stderr)
                    return 1
                score_path = matches[0] / "score.json"
            data = _j.loads(score_path.read_text(encoding="utf-8"))
        else:
            data = arch.best()
            if not data:
                print("archive empty", file=sys.stderr)
                return 1
        h = ChatTaskHarness.from_dict(data.get("harness") or data)
        path = save_active_harness(h)
        print(f"promoted to {path}")
        print(json.dumps(h.to_dict(), indent=2, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
