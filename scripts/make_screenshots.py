"""End-to-end: madcop CLI → colored HTML → PNG screenshot.

Pipeline:
    1. fork+pty so rich emits ANSI escape codes
    2. parse ANSI SGR codes → inline <span style="...">
    3. wrap in a dark terminal-themed HTML page
    4. drive cloakbrowser's chromium via headless --screenshot

Usage:
    python3 scripts/make_screenshots.py            # generate all 5 PNGs
    python3 scripts/make_screenshots.py counterfactual   # one shot
"""

from __future__ import annotations

import os
import pty
import re
import select
import subprocess
import sys
import time
from pathlib import Path

CHROMIUM = Path.home() / ".cloakbrowser/chromium-145.0.7632.109.2/Chromium.app/Contents/MacOS/Chromium"
REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "docs" / "img"

# ANSI SGR codes → CSS color/weight. We only handle the codes rich actually emits.
SGR_TO_CSS = {
    "0": "color:inherit;background:inherit;font-weight:normal;font-style:normal;text-decoration:none",
    "1": "font-weight:bold",
    "3": "font-style:italic",
    "4": "text-decoration:underline",
    "22": "font-weight:normal",
    "23": "font-style:normal",
    "24": "text-decoration:none",
    # foreground 30-37, 90-97
    "30": "color:#1e1e1e",  # black
    "31": "color:#ff5555",  # red
    "32": "color:#50fa7b",  # green
    "33": "color:#f1fa8c",  # yellow
    "34": "color:#bd93f9",  # blue/purple
    "35": "color:#ff79c6",  # magenta
    "36": "color:#8be9fd",  # cyan
    "37": "color:#f8f8f2",  # white
    "90": "color:#6272a4",  # bright black (gray)
    "91": "color:#ff6e6e",
    "92": "color:#69ff94",
    "93": "color:#ffffa5",
    "94": "color:#d6acff",
    "95": "color:#ff92df",
    "96": "color:#a4ffff",
    "97": "color:#ffffff",
}


def ansi_to_html(ansi_text: str) -> str:
    """Convert ANSI-colored terminal text to inline-styled HTML spans."""
    # Match ESC [ ... m (SGR sequences only; we ignore cursor movement).
    sgr_re = re.compile(r"\x1b\[([\d;]*)m")
    out: list[str] = []
    last_end = 0
    open_styles: list[str] = []

    for m in sgr_re.finditer(ansi_text):
        # Append plain text up to this escape
        plain = ansi_text[last_end:m.start()]
        if plain:
            # HTML-escape
            esc = (
                plain.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            if open_styles:
                out.append(f'<span style="{";".join(open_styles)}">{esc}</span>')
            else:
                out.append(esc)
        last_end = m.end()

        codes = m.group(1).split(";") if m.group(1) else ["0"]
        for code in codes:
            if code == "0" or code == "":
                open_styles = []
            elif code == "39":
                # default foreground
                open_styles = [s for s in open_styles if not s.startswith("color:")]
            elif code in SGR_TO_CSS:
                style = SGR_TO_CSS[code]
                if code in ("1", "22"):
                    if code == "1":
                        if "font-weight:bold" not in open_styles:
                            open_styles.append(style)
                    else:
                        open_styles = [s for s in open_styles if "font-weight" not in s]
                elif code in ("3", "23"):
                    if code == "3":
                        if not any("font-style:italic" in s for s in open_styles):
                            open_styles.append(style)
                    else:
                        open_styles = [s for s in open_styles if "font-style" not in s]
                elif code.startswith("color:"):
                    open_styles = [s for s in open_styles if not s.startswith("color:")]
                    open_styles.append(style)
                else:
                    open_styles.append(style)

    # Tail
    plain = ansi_text[last_end:]
    if plain:
        esc = (
            plain.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        if open_styles:
            out.append(f'<span style="{";".join(open_styles)}">{esc}</span>')
        else:
            out.append(esc)
    return "".join(out)


def capture_ansi(argv: list[str], cwd: Path | None = None, timeout: float = 8.0) -> str:
    """Run a command in a pty so rich emits ANSI codes, return text with codes."""
    master_fd, slave_fd = pty.openpty()
    pid = os.fork()
    if pid == 0:
        os.setsid()
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        os.close(master_fd)
        os.close(slave_fd)
        if cwd:
            try:
                os.chdir(cwd)
            except OSError:
                pass
        try:
            os.execvp(argv[0], argv)
        except FileNotFoundError:
            os._exit(127)
    else:
        os.close(slave_fd)
        chunks: list[bytes] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            r, _, _ = select.select([master_fd], [], [], 0.2)
            if r:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                chunks.append(data)
            elif chunks:
                # No new data for 0.2s and we already have output → likely done
                break
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
        raw = b"".join(chunks)
        return raw.replace(b"\r\n", b"\n").decode("utf-8", errors="replace")


def render_html(ansi_text: str, title: str = "madcop") -> str:
    """Wrap ANSI-parsed HTML in a dark terminal-styled page."""
    body = ansi_to_html(ansi_text)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
  html, body {{ margin: 0; padding: 0; background: #1e1e1e; }}
  body {{ padding: 28px 32px; }}
  pre {{
    background: #1e1e1e;
    color: #f8f8f2;
    padding: 0;
    margin: 0;
    font-family: ui-monospace, 'SF Mono', Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
    font-size: 13px;
    line-height: 1.45;
    white-space: pre;
    tab-size: 4;
  }}
  pre span {{ display: inline; }}
</style></head>
<body><pre>{body}</pre></body></html>
"""


def html_to_png(html_path: Path, png_path: Path, width: int = 960) -> bool:
    """Drive cloakbrowser's chromium headless to screenshot the HTML."""
    if not CHROMIUM.exists():
        print(f"  ! chromium not found at {CHROMIUM}", file=sys.stderr)
        return False
    cmd = [
        str(CHROMIUM),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--force-device-scale-factor=2",   # 2x retina
        f"--window-size={width},900",
        f"--screenshot={png_path}",
        f"file://{html_path}",
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=15, check=False)
    except subprocess.TimeoutExpired:
        print(f"  ! chromium timeout for {html_path.name}", file=sys.stderr)
        return False
    return png_path.exists() and png_path.stat().st_size > 0


DEMOS = [
    ("counterfactual", ["python3", "-m", "madcop", "run", "counterfactual"]),
    ("rca",            ["python3", "-m", "madcop", "run", "rca"]),
    ("agent",          ["python3", "-m", "madcop", "run", "agent"]),
    ("replay",         ["python3", "-m", "madcop", "replay", "examples/replay_sample.json"]),
    ("decisions",      ["python3", "-m", "madcop", "decisions", "examples/decisions_sample.jsonl"]),
]


def main(argv: list[str]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = argv[1:] if len(argv) > 1 else [name for name, _ in DEMOS]
    for name, cmd in DEMOS:
        if name not in targets:
            continue
        print(f"→ {name} ...", flush=True)
        ansi = capture_ansi(cmd, cwd=REPO_ROOT)
        if not ansi.strip():
            print(f"  ! no output captured", flush=True)
            continue
        html = render_html(ansi, title=f"madcop {name}")
        html_path = OUT_DIR / f"{name}.html"
        html_path.write_text(html, encoding="utf-8")
        png_path = OUT_DIR / f"{name}.png"
        if html_to_png(html_path, png_path):
            print(f"  ✓ {png_path} ({png_path.stat().st_size:,} bytes)", flush=True)
        else:
            print(f"  ✗ screenshot failed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))