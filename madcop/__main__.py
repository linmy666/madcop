"""madcop CLI entry point.

Two demo scenarios today:
  python -m madcop run coldchain              # W1 — print the event stream
  python -m madcop run anomalies coldchain    # W2 — run anomaly detection
"""

from __future__ import annotations

import argparse
import sys

from .adapters.wms import WMSAdapter
from .anomaly.rules import default_detector


def _format_event(idx: int, total: int, ev) -> str:
    ts = ev.parsed_timestamp.strftime("%H:%M:%S")
    val = f"{ev.value:>6.1f}°C" if ev.value is not None else "    —  "
    sev = "·" * ev.severity
    return f"  [{idx:>2}/{total}] {ts}  {val}  sev{ev.severity} {sev}  {ev.attributes.get('note', '')}"


def run_coldchain() -> int:
    """W1 demo: print the WMS cold-chain event stream."""
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


def run_anomalies_coldchain() -> int:
    """W2 demo: run all 5 anomaly rules on the cold-chain stream."""
    adapter = WMSAdapter()
    events = sorted(adapter.fetch(), key=lambda e: e.parsed_timestamp)
    detector = default_detector()
    findings = list(detector.run(events))
    print(f"madcop anomaly report — subject={events[0].subject_id if events else 'N/A'}")
    print(f"  events: {len(events)}   rules: {len(detector.rules)}   findings: {len(findings)}")
    print()
    if not findings:
        print("  (no anomalies)")
        return 0
    for i, f in enumerate(findings, 1):
        print(f"  [{i}/{len(findings)}] sev{f.severity}  {f.rule_id}")
        print(f"            {f.summary}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="madcop",
        description="madcop — the supply chain cop that goes mad for anomalies.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # run <scenario>
    run_p = sub.add_parser("run", help="Run a scenario")
    run_sub = run_p.add_subparsers(dest="scenario", required=True)
    run_sub.add_parser("coldchain", help="W1: print the cold-chain event stream")
    run_sub.add_parser("anomalies", help="W2: run anomaly detection on the cold-chain stream")

    # demo <scenario> — alias for `run`
    demo_p = sub.add_parser("demo", help="Alias for `run`")
    demo_sub = demo_p.add_subparsers(dest="scenario", required=True)
    demo_sub.add_parser("coldchain", help="W1: print the cold-chain event stream")
    demo_sub.add_parser("anomalies", help="W2: run anomaly detection on the cold-chain stream")

    args = parser.parse_args(argv)
    if args.cmd in ("run", "demo"):
        if args.scenario == "coldchain":
            return run_coldchain()
        if args.scenario == "anomalies":
            return run_anomalies_coldchain()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
