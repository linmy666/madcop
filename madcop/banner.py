"""madcop welcome banner.

A supply-chain-flavoured ASCII logo: the police head is built from
shipping containers ([====]), barcodes (||||), cargo flow arrows (>>),
and surveillance cameras ((O)).

Two visual modes:

- `render_banner_console(console)` — rich-coloured splash screen (default)
- `render_banner_plain()`           — plain text for tests / non-rich
- `splash_load(console)`           — animated progress bar (cargo flow)
- `status_panel()`                 — system status box
"""

from __future__ import annotations

import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


# --------------------------------------------------------------------------- #
# ASCII art — supply-chain cop
# --------------------------------------------------------------------------- #

# A cop head with a container-built helmet, barcode badge, camera-eyes,
# and a chip/shield core. Pure ASCII + Unicode box-drawing so it renders
# in any monospace terminal.
LOGO_LINES = [
    "",
    "               _________________________________",
    "             / [====][====][====][====][====] \\      [ CONTAINER HELMET ]",
    "            /====================================\\",
    "           ||   >>>  SUPPLY CHAIN SECURITY  >>>   ||",
    "           ----------------------------------------",
    "                       |||||||||||||||              [ BARCODE BADGE ]",
    "                    .-----------------.",
    "                   /  ___________      \\",
    "                  /  /  (O)   (O)  \\    \\           [ CAMERA EYES ]",
    "                  |  |   _|_   _|_  |   |",
    "                  |  |  /   \\ /   \\ |   |",
    "                  |  |  \\___/ \\___/ |   |",
    "                  |  |   |||||||||  |   |",
    "                  |  |   | [MAD]  |  |   |",
    "                  |  |   | [COP]  |  |   |",
    "                  |  |   |  /\\  /|  |   |           [ CHIP / SHIELD CORE ]",
    "                   \\  \\  | /  \\/ |  /  /",
    "                    \\  \\ |______| /  /",
    "                     \\  '--------'  /",
    "                      \\____________/",
    "",
    "       [======][========] [======][========]    [ CARGO-TREAD SHOULDERS ]",
    "",
]


# --------------------------------------------------------------------------- #
# Welcome message + status panel + splash
# --------------------------------------------------------------------------- #

DEPT_LINE = "DEPT: GLOBAL LOGISTICS ENFORCEMENT  //  UNIT: MADCOP-AG-01"

WELCOME_MESSAGE = (
    "I am MADCOP. Supply chain network locked.\n"
    "Monitoring every cargo node — short-shipping, lane delays, "
    "and margin arbitrage will be intercepted on sight.\n"
    "Present your credentials."
)


COMMANDS = [
    ("madcop run coldchain",            "W1: print the cold-chain event stream"),
    ("madcop run anomalies",            "W2: detect anomalies on the cold-chain stream"),
    ("madcop run rca",                  "W3: trace each anomaly to a root-cause decision"),
    ("madcop run counterfactual",       "W6: cost-simulate interventions on a TMS anomaly"),
    ("madcop run agent [--llm]",        "v0.3: full LangGraph pipeline (LLM via --llm)"),
    ("madcop replay <file.json>",       "v0.4: replay historical events, quantify ROI"),
    ("madcop decisions <file.jsonl>",   "v0.4: operator-fatigue diff over a decision log"),
    ("madcop skill new-rule NAME",      "v0.5: scaffold a new anomaly rule + test"),
    ("madcop eval <cases.jsonl>",       "v0.5: run AI PM eval harness on summarise node"),
]


# --------------------------------------------------------------------------- #
# Plain-text banner (tests + non-rich)
# --------------------------------------------------------------------------- #

def render_banner_plain(width: int = 92) -> str:
    """Plain-text banner. Used in tests and for non-rich environments."""
    out: list[str] = list(LOGO_LINES)
    out.append("  " + "─" * (width - 2))
    out.append("  madcop v0.5.0  ·  " + DEPT_LINE)
    out.append("  " + "─" * (width - 2))
    out.append("")
    out.append("  Quick commands:")
    for cmd, desc in COMMANDS:
        out.append(f"    {cmd}")
        out.append(f"      {desc}")
    out.append("")
    out.append("  Modes:")
    out.append("    - deterministic: pure-Python, no API key needed (default)")
    out.append("    - --llm: rewrite summary via OpenAI-compatible endpoint")
    out.append("         (set MADCOP_OPENAI_API_KEY / _BASE_URL / _MODEL)")
    out.append("")
    out.append("  " + "─" * (width - 2))
    out.append("  " + WELCOME_MESSAGE.replace("\n", "\n  "))
    out.append("")
    out.append("  Lin Ruihan · chuiniu@me.com · MIT License")
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Rich-coloured banner
# --------------------------------------------------------------------------- #

def _colorise_logo() -> str:
    """Apply rich colour spans to the ASCII logo."""
    spans: list[str] = []
    for line in LOGO_LINES:
        # Container helmet border (top 4 lines)
        if "[====]" in line or "SUPPLY CHAIN SECURITY" in line:
            spans.append(f"[bold cyan]{line}[/bold cyan]")
            continue
        # Barcode badge row
        if "|||||||||" in line:
            spans.append(f"[bold yellow]{line}[/bold yellow]")
            continue
        # Camera eyes
        if "(O)" in line:
            spans.append(f"[bold yellow]{line}[/bold yellow]")
            continue
        # MAD COP badge text inside the shield
        if "[MAD]" in line or "[COP]" in line:
            spans.append(f"[bold red]{line}[/bold red]")
            continue
        # Cargo-tread shoulders
        if "CARGO-TREAD" in line:
            spans.append(f"[dim cyan]{line}[/dim cyan]")
            continue
        # Annotations on the right ([ CONTAINER HELMET ] etc.)
        if line.strip().startswith("[") and line.strip().endswith("]") and "==" not in line:
            spans.append(f"[dim italic]{line}[/dim italic]")
            continue
        spans.append(line)
    return "\n".join(spans)


def status_panel() -> Panel:
    """Build the system-status panel as a Rich Panel."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="cyan", no_wrap=True)
    grid.add_column(style="white")
    grid.add_row("STATUS:",            "[bold green]ONLINE[/bold green]")
    grid.add_row("CARGO INTEGRITY:",   "[bold green]100%[/bold green]")
    grid.add_row("ROUTE OPTIMIZATION:", "[bold green]STABLE[/bold green]")
    grid.add_row("NODE SECURITY:",     "[bold green]SECURED[/bold green]")
    grid.add_row("DETECTOR RULES:",    "5 active")
    grid.add_row("LANGGRAPH PIPELINE:", "6 nodes")
    return Panel(
        grid,
        title="[bold]SUPPLY MATRIX STATUS[/bold]",
        subtitle="[dim]" + DEPT_LINE + "[/dim]",
        border_style="green",
        padding=(0, 2),
    )


def render_banner_console(console: Console | None = None, width: int = 92) -> None:
    """Print the colourful splash screen to a rich console."""
    if console is None:
        console = Console(width=128)

    # Header panel with the ASCII logo
    console.print(Panel(
        _colorise_logo(),
        title="[bold red]MAD[/bold red][bold cyan]COP[/bold cyan] [bold yellow]v0.5.0[/bold yellow]",
        subtitle="[dim]supply chain cop · AI agent framework · MIT[/dim]",
        border_style="cyan",
        padding=(0, 2),
    ))

    # Quick-commands table
    tbl = Table(
        title="[bold]Quick commands[/bold]",
        show_header=False,
        show_lines=False,
        box=None,
        padding=(0, 2),
    )
    tbl.add_column(style="cyan", no_wrap=True)
    tbl.add_column(style="white")
    for cmd, desc in COMMANDS:
        tbl.add_row(cmd, desc)
    console.print(tbl)
    console.print()

    # System status
    console.print(status_panel())
    console.print()

    # Modes
    mode_text = (
        "  [bold cyan]deterministic[/bold cyan]  pure-Python, no API key needed (default)\n"
        "  [bold cyan]--llm[/bold cyan]          rewrite summary via OpenAI-compatible endpoint\n"
        "                 set [dim]MADCOP_OPENAI_API_KEY[/dim] / [dim]_BASE_URL[/dim] / [dim]_MODEL[/dim]"
    )
    console.print(Panel(mode_text, title="[bold]Modes[/bold]", border_style="green"))
    console.print()

    # Welcome message
    console.print(Panel(
        WELCOME_MESSAGE,
        title="[bold]Greeting[/bold]",
        border_style="yellow",
        padding=(0, 2),
    ))
    console.print()

    console.print(
        "[dim]Lin Ruihan · chuiniu@me.com · "
        "[link=https://github.com/linmy666/madcop]github.com/linmy666/madcop[/link][/dim]"
    )


# --------------------------------------------------------------------------- #
# Splash progress (animated)
# --------------------------------------------------------------------------- #

def _splash_frames() -> list[str]:
    """Three frames of an animated cargo-flow progress bar."""
    return [
        "🚢 [CARG]------->>>>>[HULL]------->>>>>[ENGN] LOADING SUPPLY MATRIX [   0%]",
        "🚢 [CARG]>>>>>[HULL]>>>>>>>>>[ENGN] LOADING SUPPLY MATRIX [  60%]",
        "🚢 [CARG]>>>>>>>>>>>>>>>>[HULL]>>>>>[ENGN] LOADING SUPPLY MATRIX [ 100%]",
    ]


def splash_load(console: Console | None = None, *, animate: bool = False, delay: float = 0.05) -> None:
    """Print a brief splash animation showing cargo-matrix loading.

    With `animate=True` (default for terminal sessions), each frame is
    printed in turn with a tiny delay. With `animate=False`, only the
    final frame is shown (used in tests + non-TTY environments).
    """
    if console is None:
        console = Console()
    frames = _splash_frames()
    if not animate:
        console.print(f"[cyan]{frames[-1]}[/cyan]")
        return
    for frame in frames:
        console.print(f"[cyan]{frame}[/cyan]")
        time.sleep(delay)


__all__ = [
    "COMMANDS",
    "DEPT_LINE",
    "LOGO_LINES",
    "WELCOME_MESSAGE",
    "render_banner_console",
    "render_banner_plain",
    "splash_load",
    "status_panel",
]