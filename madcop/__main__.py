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
from .rca.graph import explain, trace
from .rca.seed import build_coldchain_seed


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


def run_rca_coldchain() -> int:
    """W3 demo: detect anomalies and trace each to a root-cause decision."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    events = sorted(WMSAdapter().fetch(), key=lambda e: e.parsed_timestamp)
    findings = list(default_detector().run(events))
    g = build_coldchain_seed()

    console.print(f"[bold]madcop RCA demo[/] — {len(findings)} finding(s) on {events[0].subject_id}\n")
    if not findings:
        console.print("  [dim](no findings to trace)[/]")
        return 0
    for i, f in enumerate(findings, 1):
        console.print(f"[cyan]━━━ finding {i}/{len(findings)} ━━━[/]")
        console.print(f"  rule:    [yellow]{f.rule_id}[/]")
        console.print(f"  summary: {f.summary}")
        chain = trace(f, g)
        if not chain.steps:
            console.print("  [dim](no causal chain — subject not in knowledge graph)[/]")
            continue
        console.print(f"  chain:   [bold]{len(chain.steps)}[/] step(s), root cause:")
        console.print(Panel(explain(chain), title="root cause", border_style="red"))
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
    run_sub.add_parser("rca",       help="W3: detect anomalies and trace each to a root cause")

    # demo <scenario> — alias for `run`
    demo_p = sub.add_parser("demo", help="Alias for `run`")
    demo_sub = demo_p.add_subparsers(dest="scenario", required=True)
    demo_sub.add_parser("coldchain", help="W1: print the cold-chain event stream")
    demo_sub.add_parser("anomalies", help="W2: run anomaly detection on the cold-chain stream")
    demo_sub.add_parser("rca",       help="W3: detect anomalies and trace each to a root cause")

    args = parser.parse_args(argv)
    if args.cmd in ("run", "demo"):
        if args.scenario == "coldchain":
            return run_coldchain()
        if args.scenario == "anomalies":
            return run_anomalies_coldchain()
        if args.scenario == "rca":
            return run_rca_coldchain()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
