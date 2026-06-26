"""madcop CLI entry point.

Six demo scenarios today:
  python -m madcop run coldchain              # W1 — print the event stream
  python -m madcop run anomalies coldchain    # W2 — run anomaly detection
  python -m madcop run rca                    # W3 — RCA on cold-chain stream
  python -m madcop run counterfactual         # W6 — cost-simulate interventions
  python -m madcop run agent [--llm]          # v0.3 — LangGraph orchestration
  python -m madcop replay <file.json>         # v0.4 — anomaly replay + ROI
  python -m madcop decisions <file.jsonl>     # v0.4 — operator-fatigue diff
  python -m madcop skill new-rule NAME        # v0.5 — scaffold new anomaly rule
  python -m madcop skill new-adapter NAME     # v0.5 — scaffold new data adapter
  python -m madcop skill new-cost NAME        # v0.5 — scaffold new cost function
  python -m madcop eval cases.jsonl           # v0.5 — run AI PM eval harness
"""

from __future__ import annotations

import argparse
import os
import sys

from .adapters.wms import WMSAdapter
from .agent import run_agent
from .anomaly.rules import default_detector
from .banner import render_banner_console, splash_load
from .counterfactual import compare_all
from .decision import DecisionDiff, load_decision_log
from .llm import MockClient, OpenAICompatClient
from .replay import ReplayEngine, load_events_from_json
from .rca.graph import explain, trace
from .rca.seed import build_coldchain_seed


def _format_event(idx: int, total: int, ev) -> str:
    ts = ev.parsed_timestamp.strftime("%H:%M:%S")
    val = f"{ev.value:>6.1f}°C" if ev.value is not None else "    —  "
    sev = "·" * ev.severity
    return f"  [{idx:>2}/{total}] {ts}  {val}  sev{ev.severity} {sev}  {ev.attributes.get('note', '')}"


def _splash_header(label: str) -> None:
    """Brief cargo-flow progress bar shown before scenario demos."""
    from rich.console import Console
    splash_load(Console(width=128), animate=False)
    Console(width=128).print(f"  [dim cyan]running:[/] [bold]{label}[/bold]")


def run_coldchain() -> int:
    """W1 demo: print the WMS cold-chain event stream."""
    from rich.console import Console
    _splash_header("W1 cold-chain event stream")
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
    _splash_header("W2 anomaly detection on cold-chain stream")
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

    _splash_header("W3 root-cause analysis")
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

    _splash_header("W6 counterfactual cost simulation")
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


def run_agent_demo(use_llm: bool = False) -> int:
    """v0.3 demo: run the full LangGraph agent on the WMS cold-chain stream.

    With --llm, the summarise node calls a real LLM (set MADCOP_OPENAI_API_KEY
    etc.). Without --llm, it uses the deterministic pure-Python summary.

    This exercises every layer end-to-end:
    ingest_events → detect → maybe_replan → counterfactual → summarise
    """
    from rich.console import Console
    from rich.panel import Panel

    _splash_header("v0.3+ LangGraph agent")
    console = Console()
    events = sorted(WMSAdapter().fetch(), key=lambda e: e.parsed_timestamp)
    console.print(f"[bold]madcop agent demo[/] — {len(events)} events from WMSAdapter\n")

    chat_client = None
    if use_llm:
        try:
            chat_client = OpenAICompatClient()
            console.print("  [dim]LLM mode: OpenAI-compatible endpoint active[/]")
        except ValueError as e:
            console.print(f"  [red]LLM init failed:[/] {e}")
            console.print("  [yellow]Falling back to deterministic summary[/]")
            chat_client = None
    else:
        console.print("  [dim]Deterministic mode (no LLM). Use --llm to enable.[/]")

    state = run_agent(
        events, default_detector(),
        chat_client=chat_client, use_llm=use_llm,
    )

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
    console.print(f"  summarise:        {'LLM-rewritten' if use_llm and chat_client else 'deterministic'}")

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


def run_skill(action: str, name: str) -> int:
    """v0.5: scaffold a new component (rule / adapter / cost function).

    Writes a starter .py file with TODOs and a paired test file, into the
    current working directory. The user fills in the TODOs and runs pytest.
    """
    from rich.console import Console
    from pathlib import Path
    from .skill import (
        render_new_adapter, render_new_cost, render_new_rule,
    )

    console = Console()
    target_dir = Path.cwd()
    if action == "new-rule":
        rule_path, test_path = render_new_rule(name, target_dir)
        files = (rule_path, test_path)
        hint = (
            f"edit {rule_path.name}, implement evaluate(), then run `pytest "
            f"{test_path.name}`"
        )
    elif action == "new-adapter":
        rule_path, test_path = render_new_adapter(name, target_dir)
        files = (rule_path, test_path)
        hint = (
            f"edit {rule_path.name}, connect to your data source in execute(), "
            f"then run `pytest {test_path.name}`"
        )
    elif action == "new-cost":
        rule_path, test_path = render_new_cost(name, target_dir)
        files = (rule_path, test_path)
        hint = (
            f"edit {rule_path.name}, subclass CounterfactualEngine, "
            f"then run `pytest {test_path.name}`"
        )
    else:
        console.print(f"[red]unknown skill action:[/] {action}")
        console.print("  valid: new-rule, new-adapter, new-cost")
        return 2

    for p in files:
        console.print(f"  [green]✓[/] wrote [cyan]{p}[/]")
    console.print(f"\n[dim]{hint}[/]")
    return 0


def run_eval(jsonl_path: str) -> int:
    """v0.5: run an AI-PM eval harness against a cases file.

    Each line of the JSONL file is an EvalCase:
        {"name": "...", "prompt": "...", "scorer": "contains|regex|max_length",
         "needle": "...", "pattern": "...", "max_length": 100}
    """
    import json
    from rich.console import Console
    from rich.table import Table
    from .eval import EvalRunner, EvalCase, contains, regex_match, max_length

    console = Console()
    try:
        with open(jsonl_path) as f:
            raw_cases = [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        console.print(f"[red]file not found:[/] {jsonl_path}")
        return 2

    runner = EvalRunner()
    for c in raw_cases:
        scorer_type = c.get("scorer", "contains")
        if scorer_type == "contains":
            scorer = contains(c["needle"], case_sensitive=c.get("case_sensitive", True))
        elif scorer_type == "regex":
            scorer = regex_match(c["pattern"])
        elif scorer_type == "max_length":
            scorer = max_length(c["max_length"])
        else:
            console.print(f"[red]unknown scorer:[/] {scorer_type}")
            return 2
        runner.add(EvalCase(
            name=c["name"],
            prompt=c["prompt"],
            scorer=scorer,
            system_prompt=c.get("system_prompt"),
        ))

    # The eval agent is the deterministic summary from madcop's own state.
    from .adapters.wms import WMSAdapter
    from .agent import run_agent as _run_agent

    def eval_agent(prompt, system_prompt):
        # Trivial "agent" — for v0.5 the eval just exercises the summarise node.
        events = sorted(WMSAdapter().fetch(), key=lambda e: e.parsed_timestamp)
        state = _run_agent(events, default_detector())
        return state.get("summary", "")

    console.print(f"[bold]madcop eval[/] — {len(runner.cases)} case(s) from [cyan]{jsonl_path}[/]\n")
    report = runner.run(eval_agent)
    tbl = Table(title="eval results", show_lines=False)
    tbl.add_column("case", style="bold")
    tbl.add_column("verdict", justify="center")
    tbl.add_column("detail")
    for r in report.results:
        verdict = "[green]PASS[/]" if r.passed else "[red]FAIL[/]"
        tbl.add_row(r.case_name, verdict, r.detail)
    console.print(tbl)
    console.print(
        f"\n[bold]summary:[/] {report.passed}/{report.total} passed "
        f"({report.pass_rate:.0%})"
    )
    return 0 if report.all_passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="madcop",
        description="madcop — the supply chain cop that goes mad for anomalies.",
    )
    sub = parser.add_subparsers(dest="cmd")

    # run <scenario>
    run_p = sub.add_parser("run", help="Run a scenario")
    run_sub = run_p.add_subparsers(dest="scenario", required=True)
    run_sub.add_parser("coldchain", help="W1: print the cold-chain event stream")
    run_sub.add_parser("anomalies", help="W2: run anomaly detection on the cold-chain stream")
    run_sub.add_parser("rca",       help="W3: detect anomalies and trace each to a root cause")
    run_sub.add_parser("counterfactual", help="W6: cost-simulate interventions for each TMS anomaly")
    agent_p = run_sub.add_parser("agent", help="v0.3+: run the full LangGraph agent end-to-end")
    agent_p.add_argument("--llm", action="store_true",
                         help="Rewrite the summary via a real LLM (OpenAI-compatible). "
                              "Reads MADCOP_OPENAI_API_KEY / _BASE_URL / _MODEL from env.")
    # v0.6.0+ agent: plan-execute loop + multi-model router + 4-layer memory
    agent_v6_p = run_sub.add_parser("agent-v6", help="v0.6.0+: plan-execute loop with multi-model routing + 4-layer memory")
    agent_v6_p.add_argument("goal", nargs="?", default="diagnose the last 24h of OMS events",
                            help="What should the agent do? (default: diagnose OMS last 24h)")
    agent_v6_p.add_argument("--mode", choices=["flash", "standard", "pro", "ultra"],
                            default="standard", help="Execution mode (default: standard)")
    agent_v6_p.add_argument("--llm", action="store_true",
                            help="Use a real LLM (env: MADCOP_OPENAI_*)")
    agent_v6_p.add_argument("--subagents", action="store_true",
                            help="Enable sub-agent fan-out (v0.7.0)")
    agent_v6_p.add_argument("--no-memory", action="store_true",
                            help="Skip memory read/write (default: memory is on)")

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

    # skill <action> <name> — v0.5 scaffolder
    skill_p = sub.add_parser("skill", help="v0.5: scaffold a new component")
    skill_sub = skill_p.add_subparsers(dest="skill_action", required=True)
    for action, desc in [
        ("new-rule", "scaffold a custom anomaly rule + test"),
        ("new-adapter", "scaffold a custom data adapter + test"),
        ("new-cost", "scaffold a custom counterfactual cost function + test"),
    ]:
        sp = skill_sub.add_parser(action, help=desc)
        sp.add_argument("name", help="snake_case name (e.g. my_check, store_orders)")

    # eval <file.jsonl> — v0.5 AI PM eval harness
    eval_p = sub.add_parser("eval", help="v0.5: run AI PM eval cases against madcop's summarise node")
    eval_p.add_argument("file", help="JSONL file of EvalCase records")

    # config <action> — v0.7.1 config management
    config_p = sub.add_parser("config", help="v0.7.1: manage ~/.madcop/config.yaml")
    config_sub = config_p.add_subparsers(dest="config_action", required=True)
    config_sub.add_parser("init", help="Write a default config to ~/.madcop/config.yaml")
    config_sub.add_parser("show", help="Print the resolved config (with env-var resolution)")
    config_p.add_argument("--path", help="Override the config file path")

    # plan <goal> — v0.6.0+ shortcut for `run agent-v6`
    plan_p = sub.add_parser("plan", help="v0.6.0+: run the plan-execute loop on a free-text goal")
    plan_p.add_argument("goal", nargs="?", default="diagnose the last 24h of OMS events",
                        help="What should the agent do?")
    plan_p.add_argument("--mode", choices=["flash", "standard", "pro", "ultra"],
                        default="standard")
    plan_p.add_argument("--llm", action="store_true",
                        help="Use a real LLM (env: MADCOP_OPENAI_*)")
    plan_p.add_argument("--subagents", action="store_true",
                        help="Enable sub-agent fan-out (v0.7.0)")

    # v0.8.0: self-check CLI
    doctor_p = sub.add_parser(
        "doctor", help="v0.8.0: run a self-check (env, LLM, scratchpad, sub-agents)"
    )
    doctor_p.add_argument("--strict", action="store_true",
                          help="Treat missing LLM env vars as a fail (not a warn)")
    doctor_p.add_argument("--json", action="store_true",
                          help="Output the report as JSON instead of pretty text")

    args = parser.parse_args(argv)
    if args.cmd is None:
        from .banner import render_banner_console
        render_banner_console()
        return 0
    if args.cmd == "replay":
        return run_replay(args.file)
    if args.cmd == "decisions":
        return run_decisions(args.file)
    if args.cmd == "skill":
        return run_skill(args.skill_action, args.name)
    if args.cmd == "eval":
        return run_eval(args.file)
    if args.cmd == "config":
        from .config import load_config, save_default_config, DEFAULT_CONFIG_PATH, resolve_provider
        if args.config_action == "init":
            from pathlib import Path as _P
            target = _P(args.path).expanduser() if args.path else DEFAULT_CONFIG_PATH
            existed = target.exists()
            out = save_default_config(target, overwrite=False)
            if existed:
                print(f"config already exists at: {out} (not overwritten). Use a different --path or delete the file.")
            else:
                print(f"wrote default config to: {out}")
            return 0
        if args.config_action == "show":
            cfg = load_config(args.path or DEFAULT_CONFIG_PATH)
            print(f"config path: {cfg.config_path}")
            print("providers:")
            for name, p in cfg.providers.items():
                print(f"  {name}: {p.base_url} model={p.model}")
                resolved = resolve_provider(cfg, name)
                print(f"    api_key (resolved): {resolved.api_key[:8]}...{resolved.api_key[-4:] if len(resolved.api_key) > 12 else ''}")
            print(f"router: mode={cfg.router.mode}")
            print(f"        manual_tier={cfg.router.manual_tier}")
            print(f"cost: budget_per_run_usd={cfg.cost.budget_per_run_usd}")
            print(f"memory: path={cfg.memory.path}, growth={cfg.memory.growth_enabled}, "
                  f"auto_distill={cfg.memory.auto_distill}, auto_feedback={cfg.memory.auto_feedback}")
            return 0
    if args.cmd == "plan":
        return run_agent_v6(
            goal=args.goal,
            mode=args.mode,
            use_llm=args.llm,
            use_subagents=args.subagents,
        )
    if args.cmd == "doctor":
        return run_doctor(strict=args.strict, as_json=args.json)
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
            return run_agent_demo(use_llm=getattr(args, "llm", False))
        if args.scenario == "agent-v6":
            return run_agent_v6(
                goal=args.goal,
                mode=args.mode,
                use_llm=args.llm,
                use_subagents=args.subagents,
            )
    parser.print_help()
    return 2


def run_doctor(strict: bool = False, as_json: bool = False) -> int:
    """v0.8.0: self-check CLI — print the report, return 0/1."""
    from .doctor import run_all_checks
    from rich.console import Console

    report = run_all_checks(strict=strict)
    if as_json:
        import json
        print(json.dumps(
            {"passed": report.passed,
             "failures": report.failure_count,
             "warnings": report.warn_count,
             "checks": [{"name": c.name, "status": c.status,
                         "detail": c.detail, "fix": c.fix}
                        for c in report.checks]},
            indent=2, ensure_ascii=False,
        ))
    else:
        console = Console()
        for line in report.to_text().splitlines():
            console.print(line)
    return 0 if report.passed else 1


# --------------------------------------------------------------------------- #
# v0.6.0+ plan-execute runner (CLI hook)
# --------------------------------------------------------------------------- #


def run_agent_v6(goal: str, mode: str = "standard", use_llm: bool = False, use_subagents: bool = False) -> int:
    """v0.6.0+ plan-execute demo: walk a free-text goal through the new loop.

    - mode: flash | standard | pro | ultra
    - use_llm: build a real LLM-backed step executor + memory growth
    - use_subagents: build a SubagentExecutor + LLMRunner for v0.7.0 fan-out
    """
    from rich.console import Console
    from rich.panel import Panel

    console = Console()

    # 1. Build the LLM client (real or mock)
    chat_client = None
    if use_llm:
        from .llm import OpenAICompatClient, MockClient
        try:
            chat_client = OpenAICompatClient()
            console.print(f"  [dim]LLM:[/] {chat_client.model} @ {chat_client.base_url}")
        except ValueError as e:
            console.print(f"  [red]LLM init failed:[/] {e}")
            console.print("  [yellow]Falling back to MockClient[/]")
            chat_client = MockClient()
    else:
        from .llm import MockClient
        chat_client = MockClient()
        console.print("  [dim]Using MockClient (pass --llm for real LLM)[/]")

    # 2. Build the sub-agent layer (v0.7.0)
    from .agent.subagent import (
        SubagentExecutor, ExecutorConfig, LLMRunner,
    )
    subagent_executor = SubagentExecutor(
        runner=LLMRunner(chat_client, max_tokens=512, temperature=0.0),
        config=ExecutorConfig(max_concurrent=2),
        parent_tools=("read", "write", "bash"),
    ) if use_subagents else None

    # 3. Build the step router (inline + sub-agent dispatch)
    from .agent.plan_execute import (
        ExecutionMode, FnStepExecutor, Plan, PlanExecuteConfig,
        PlanExecuteLoop, PlanStep, StepOutcome,
    )
    from .anomaly.detector import Detector
    from .anomaly.rules import ColdChainTemperatureRule, OMSOrderCancelSpikeRule
    from .memory import (
        MemoryStore, EpisodicMemory, SemanticMemory, ReflectiveMemory, GrowthEngine,
    )
    from .memory.episodic import EpisodeOutcome
    from .memory.growth import GrowthConfig

    detector = Detector(rules=[OMSOrderCancelSpikeRule(), ColdChainTemperatureRule()])

    def router_fn(step: PlanStep, ctx: dict) -> StepOutcome:
        if step.subagent is not None and subagent_executor is not None:
            # Dispatch to sub-agent
            results = subagent_executor.run_many([(step.subagent, step.action, ctx)])
            r = results[0]
            return StepOutcome(
                step_name=step.name,
                output=r.result or "",
                success=(r.status.value == "completed"),
                cost_usd=r.cost_usd,
                duration_s=r.duration_s or 0.0,
                error=r.error,
            )
        # Inline step: call LLM with the step's action as the prompt
        from .llm import Message
        try:
            resp = chat_client.chat([Message(role="user", content=step.action)])
            content = resp.content
            if "<think>" in content and "</think>" in content:
                content = content.split("</think>", 1)[-1].strip()
            return StepOutcome(step_name=step.name, output=content, success=True,
                               cost_usd=0.001, duration_s=0.01)
        except Exception as e:
            return StepOutcome(step_name=step.name, output="", success=False,
                               error=f"{type(e).__name__}: {e}")

    # 4. Build a simple 3-step plan from the goal
    plan = Plan(steps=[
        PlanStep(name="explain", action=f"Explain in 1 sentence: {goal}"),
        PlanStep(name="outline", action=f"Outline 2 next steps to address: {goal}"),
        PlanStep(name="summarise", action=f"Concise summary (1 paragraph) of: {goal}"),
    ])

    class FixedPlanner:
        def plan(self, g, m):  # noqa: ARG002
            return plan

    # 5. Build the loop
    loop = PlanExecuteLoop(
        FixedPlanner(),
        FnStepExecutor(router_fn),
        PlanExecuteConfig(mode=ExecutionMode(mode)),
    )

    import time
    t0 = time.time()
    result = loop.run(goal)
    elapsed = time.time() - t0

    console.print()
    console.print(f"  [dim]goal:[/] {goal}")
    console.print(f"  [dim]mode:[/] {result.mode.value}")
    console.print(f"  [dim]success:[/] {result.success}")
    console.print(f"  [dim]cost:[/] ${result.total_cost_usd:.4f}")
    console.print(f"  [dim]elapsed:[/] {elapsed:.2f}s")
    console.print()
    for o in result.step_outcomes:
        status = "[green]OK[/]" if o.success else "[red]FAIL[/]"
        sub = " (sub-agent)" if o.step_name in {"explain", "outline", "summarise"} and subagent_executor else ""
        console.print(f"  {status} {o.step_name}{sub}: {o.output[:200]}")
    console.print()
    console.print(Panel(result.final_output, title="agent-v6 report", border_style="green"))

    if subagent_executor is not None:
        subagent_executor.shutdown(wait=False)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
