"""madcop CLI entry point.

Six demo scenarios today:
  python -m madcop run coldchain              # W1 — print the event stream
  python -m madcop run anomalies coldchain    # W2 — run anomaly detection
  python -m madcop run rca                    # W3 — RCA on cold-chain stream
  python -m madcop run counterfactual         # W6 — cost-simulate interventions
  python -m madcop run agent                  # v0.3 — LangGraph orchestration
  python -m madcop replay <file.json>         # v0.4 — anomaly replay + ROI
  python -m madcop decisions <file.jsonl>     # v0.4 — operator-fatigue diff
"""

from __future__ import annotations

import argparse
import sys

from .adapters.wms import WMSAdapter
from .agent import run_agent
from .anomaly.rules import default_detector
from .counterfactual import compare_all
from .decision import DecisionDiff, load_decision_log
from .replay import ReplayEngine, load_events_from_json
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


def run_counterfactual() -> int:
    """W6 demo: cost-simulate interventions for TMS-related anomalies.

    The WMSAdapter demo only emits WMS events (no TMS data), so we
    construct a small synthetic TMS finding + OMS order stream here.
    This keeps the WMSAdapter focused on WMS and gives the counterfactual
    demo a meaningful scenario to cost.
    """
    from rich.console import Console
    from rich.table import Table

    from .anomaly.detector import AnomalyFinding
    from .event import (
        EventType, SourceSystem, make_event,
    )

    console = Console()

    # Synthetic scenario: shipment SHIP-X was supposed to arrive by 10:00.
    # 12 OMS orders in the next 4h depend on it. The rule fired sev=4
    # (60-min overrun expected) at 10:00.
    f = AnomalyFinding(
        rule_id="tms.leadtime.overrun",
        subject_id="SHIP-X",
        timestamp="2026-06-15T10:00:00Z",
        severity=4,
        summary="Shipment SHIP-X took 6.0h vs. planned 4.0h (+50%)",
        details={"actual_hours": 6.0, "planned_hours": 4.0, "overrun_ratio": 0.5},
    )
    # 12 orders, one every 20 minutes
    oms_events = [
        make_event(
            timestamp=f"2026-06-15T{10 + (i // 3):02d}:{(i % 3) * 20:02d}:00Z",
            source_system=SourceSystem.OMS,
            event_type=EventType.ORDER_PLACED,
            subject_id="STORE-A",
            attributes={"category": "dairy"},
        )
        for i in range(12)
    ]

    console.print(f"[bold]madcop counterfactual demo[/] — synthetic TMS finding\n")
    console.print(f"  rule:    [yellow]{f.rule_id}[/]  sev={f.severity}")
    console.print(f"  summary: {f.summary}")
    console.print(f"  orders:  12 OMS orders in 4h window\n")

    outcomes = compare_all(f, oms_events)
    tbl = Table(title="intervention cost comparison", show_lines=False)
    tbl.add_column("intervention", style="bold")
    tbl.add_column("cost ¥", justify="right")
    tbl.add_column("Δ vs baseline ¥", justify="right")
    tbl.add_column("verdict")
    baseline = outcomes[0].baseline_total_yuan
    for o in outcomes:
        delta = o.intervention_total_yuan - baseline
        verdict = o.recommend().split(":")[0]
        tbl.add_row(
            o.intervention.kind.value,
            f"{o.intervention_total_yuan:,.0f}",
            f"{delta:+,.0f}",
            verdict,
        )
    console.print(tbl)
    best = outcomes[0]
    console.print(
        f"\n[green]→ best action:[/] [bold]{best.intervention.kind.value}[/] "
        f"@ ¥{best.intervention_total_yuan:,.0f} "
        f"(saves ¥{abs(best.delta_yuan):,.0f} vs. baseline)"
    )
    return 0


def run_agent_demo() -> int:
    """v0.3 demo: run the full LangGraph agent on the WMS cold-chain stream.

    This exercises every layer end-to-end:
    ingest_events → detect → maybe_replan → counterfactual → summarise
    """
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    events = sorted(WMSAdapter().fetch(), key=lambda e: e.parsed_timestamp)
    console.print(f"[bold]madcop agent demo[/] — {len(events)} events from WMSAdapter\n")

    state = run_agent(events, default_detector())

    # Step-by-step trace
    console.print("[cyan]━━━ graph execution ━━━[/]")
    console.print(f"  ingest_events:    sorted {len(events)} events")
    console.print(f"  detect:           {len(state.get('findings', []))} finding(s)")
    console.print(
        f"  maybe_replan:     triggered={state.get('replan_triggered', False)}"
        + (
            f", new SS={state.get('new_safety_stock', 0):.1f} units "
            f"for {state.get('new_safety_stock_sku', '')}"
            if state.get("replan_triggered")
            else ""
        )
    )
    console.print(f"  counterfactual:   {len(state.get('counterfactual_results', []))} outcome(s)")
    console.print(f"  summarise:        1 paragraph")

    console.print()
    console.print(Panel(state.get("summary", ""), title="agent summary", border_style="green"))
    return 0


def run_replay(json_path: str) -> int:
    """v0.4 demo: replay a historical event file and quantify the ROI of
    adopting every madcop recommendation.
    """
    from rich.console import Console
    from rich.table import Table

    console = Console()
    try:
        events = load_events_from_json(json_path)
    except FileNotFoundError:
        console.print(f"[red]file not found:[/] {json_path}")
        return 2
    except (ValueError, KeyError) as e:
        console.print(f"[red]invalid event file:[/] {e}")
        return 2

    console.print(f"[bold]madcop replay[/] — {len(events)} events from [cyan]{json_path}[/]\n")

    engine = ReplayEngine(default_detector())
    report = engine.run(events)

    console.print(
        f"[cyan]━━━ ROI summary ━━━[/]\n"
        f"  anomalies:  {report.n_findings}\n"
        f"  actual loss (do-nothing):   [red]¥{report.total_actual_loss_yuan:,.0f}[/]\n"
        f"  simulated loss (adopt rec): [green]¥{report.total_simulated_loss_yuan:,.0f}[/]\n"
        f"  POTENTIAL SAVINGS:          [bold green]¥{report.total_savings_yuan:,.0f}[/] "
        f"({report.savings_pct:.1%})\n"
    )

    if report.n_findings == 0:
        console.print("  [dim](no actionable findings in this stream)[/]")
        return 0

    tbl = Table(title="per-finding recommendations", show_lines=False)
    tbl.add_column("rule", style="bold")
    tbl.add_column("subject")
    tbl.add_column("sev", justify="center")
    tbl.add_column("recommendation", style="green")
    tbl.add_column("saves ¥", justify="right")
    tbl.add_column("saves %", justify="right")
    for fr in report.findings:
        tbl.add_row(
            fr.finding.rule_id,
            fr.finding.subject_id,
            str(fr.finding.severity),
            fr.recommendation.value,
            f"{fr.savings_yuan:,.0f}",
            f"{fr.savings_pct:.0%}",
        )
    console.print(tbl)
    return 0


def run_decisions(jsonl_path: str) -> int:
    """v0.4 demo: compute operator-fatigue diff over a decision log.

    Each line of the JSONL file is a `DecisionRecord`. The output surfaces
    the cases where madcop keeps recommending the same action but humans
    keep rejecting/ignoring it.
    """
    from rich.console import Console
    from rich.table import Table

    console = Console()
    try:
        log = load_decision_log(jsonl_path)
    except FileNotFoundError:
        console.print(f"[red]file not found:[/] {jsonl_path}")
        return 2
    except (ValueError, KeyError) as e:
        console.print(f"[red]invalid decision log:[/] {e}")
        return 2

    console.print(f"[bold]madcop decisions[/] — {len(log)} record(s) from [cyan]{jsonl_path}[/]\n")
    if len(log) == 0:
        console.print("  [dim](empty log)[/]")
        return 0

    rep = DecisionDiff(min_ignore_rate=0.5, min_occurrences=2).run(log)

    tbl = Table(title="all (rule, subject) groups", show_lines=False)
    tbl.add_column("signature", style="bold")
    tbl.add_column("occurrences", justify="right")
    tbl.add_column("accepted", justify="right")
    tbl.add_column("ignored", justify="right")
    tbl.add_column("ignore rate", justify="right")
    tbl.add_column("last seen")
    for r in rep.rows:
        ignored = r.n_occurrences - r.n_accepted
        tbl.add_row(
            r.signature,
            str(r.n_occurrences),
            str(r.n_accepted),
            str(ignored),
            f"{r.ignore_rate:.0%}",
            r.last_seen_at,
        )
    console.print(tbl)

    if rep.ignored_recommendations:
        console.print(f"\n[bold yellow]⚠ operator-fatigue signals ({len(rep.ignored_recommendations)}):[/]")
        for r in rep.ignored_recommendations[:5]:
            console.print(
                f"  • [bold]{r.signature}[/] — madcop recommended {r.n_occurrences}× "
                f"but operators accepted only {r.n_accepted}× ({r.ignore_rate:.0%} ignored)"
            )
    else:
        console.print("\n[green]✓ no operator-fatigue signals[/] (all recommendations followed)")
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
    run_sub.add_parser("counterfactual", help="W6: cost-simulate interventions for each TMS anomaly")
    run_sub.add_parser("agent",     help="v0.3: run the full LangGraph agent end-to-end")

    # demo <scenario> — alias for `run`
    demo_p = sub.add_parser("demo", help="Alias for `run`")
    demo_sub = demo_p.add_subparsers(dest="scenario", required=True)
    demo_sub.add_parser("coldchain", help="W1: print the cold-chain event stream")
    demo_sub.add_parser("anomalies", help="W2: run anomaly detection on the cold-chain stream")
    demo_sub.add_parser("rca",       help="W3: detect anomalies and trace each to a root cause")
    demo_sub.add_parser("counterfactual", help="W6: cost-simulate interventions for each TMS anomaly")
    demo_sub.add_parser("agent",     help="v0.3: run the full LangGraph agent end-to-end")

    # replay <file.json> — v0.4 anomaly replay + ROI
    replay_p = sub.add_parser("replay", help="v0.4: replay a historical event file and quantify ROI")
    replay_p.add_argument("file", help="JSON file of events (see README for format)")

    # decisions <file.jsonl> — v0.4 operator-fatigue diff
    dec_p = sub.add_parser("decisions", help="v0.4: diff a decision log and surface operator-fatigue signals")
    dec_p.add_argument("file", help="JSONL file of decision records (timestamp, rule_id, ...)")

    args = parser.parse_args(argv)
    if args.cmd == "replay":
        return run_replay(args.file)
    if args.cmd == "decisions":
        return run_decisions(args.file)
    if args.cmd in ("run", "demo"):
        if args.scenario == "coldchain":
            return run_coldchain()
        if args.scenario == "anomalies":
            return run_anomalies_coldchain()
        if args.scenario == "rca":
            return run_rca_coldchain()
        if args.scenario == "counterfactual":
            return run_counterfactual()
        if args.scenario == "agent":
            return run_agent_demo()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
