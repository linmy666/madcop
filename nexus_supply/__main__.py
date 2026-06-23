"""L1 demo entry point — print the cold-chain event stream.

This is the W1 "done" condition. If this prints a sensible timeline, the
unified event layer works and the WMS adapter shape is right.

Run with:
    python -m nexus_supply run coldchain
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from .adapters.wms import WMSAdapter


def _format_event(idx: int, total: int, ev) -> str:
    ts = ev.parsed_timestamp.strftime("%H:%M:%S")
    val = f"{ev.value:>6.1f}°C" if ev.value is not None else "    —  "
    sev = "·" * ev.severity  # 1..5 dots, visual severity
    return f"  [{idx:>2}/{total}] {ts}  {val}  sev{ev.severity} {sev}  {ev.attributes.get('note', '')}"


def run_coldchain() -> int:
    adapter = WMSAdapter()
    events = sorted(adapter.fetch(), key=lambda e: e.parsed_timestamp)
    if not events:
        print("(no events)", file=sys.stderr)
        return 1
    print(f"cold-chain timeline for {events[0].subject_id}")
    print(f"  threshold: {adapter.COLD_CHAIN_THRESHOLD_C}°C")
    print()
    for i, ev in enumerate(events, 1):
        print(_format_event(i, len(events), ev))
    breaches = [e for e in events if e.value is not None and e.value > adapter.COLD_CHAIN_THRESHOLD_C]
    print()
    print(f"  → {len(breaches)} threshold breach(es) detected")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nexus-supply",
        description="Pluggable LangGraph framework for supply chain anomaly orchestration.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="Run a scenario")
    run_sub = run_p.add_subparsers(dest="scenario", required=True)
    run_sub.add_parser("coldchain", help="Print the W1 cold-chain event stream")
    args = parser.parse_args(argv)
    if args.cmd == "run" and args.scenario == "coldchain":
        return run_coldchain()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
