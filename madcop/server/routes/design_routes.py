"""Design workshop routes — hybrid PM prototype tool.

Files live in ~/.madcop/preview/ (already served at /preview). The
agent writes prototypes there via normal chat; this router gives the
UI read/write access so PMs can hand-edit the HTML when the model
hallucinates — natural language and manual editing combined.

Generation: one non-streaming LLM call with a prototype-spec system
prompt (mobile viewport, states checklist, realistic content, zero
dependencies). The UI shows a progress state while it runs.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

_PREVIEW_DIR = Path.home() / ".madcop" / "preview"
_MAX_HTML_BYTES = 1_500_000


def _safe_name(name: str) -> str:
    """Confine every file operation to the preview dir: strip paths,
    sanitize the stem (dots in the stem become underscores), force a
    single .html extension. The extension is handled BEFORE sanitizing
    so `foo.html` never mangles into `foo_html.html`."""
    base = (name or "").strip()
    base = base.replace("\\", "/").split("/")[-1]
    if base.lower().endswith(".html"):
        stem, ext = base[:-5], ".html"
    else:
        stem, ext = base, ".html"
    stem = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]", "_", stem) or "untitled"
    return stem + ext


@router.get("/api/v4/design/files")
async def design_files() -> dict[str, Any]:
    """List prototype HTML files (newest first)."""
    _PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for p in sorted(_PREVIEW_DIR.glob("*.html"),
                    key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            files.append({
                "name": p.name,
                "size": p.stat().st_size,
                "mtime": int(p.stat().st_mtime),
            })
        except OSError:
            continue
    return {"ok": True, "dir": str(_PREVIEW_DIR), "files": files}


@router.get("/api/v4/design/file")
async def design_file(name: str = "") -> dict[str, Any]:
    fname = _safe_name(name)
    p = _PREVIEW_DIR / fname
    if not p.exists():
        raise HTTPException(404, f"prototype not found: {fname}")
    content = p.read_text(encoding="utf-8", errors="replace")
    return {"ok": True, "name": fname, "content": content[:_MAX_HTML_BYTES]}


@router.delete("/api/v4/design/file")
async def design_file_delete(name: str = "") -> dict[str, Any]:
    fname = _safe_name(name)
    p = _PREVIEW_DIR / fname
    if p.exists():
        p.unlink()
    return {"ok": True, "deleted": fname}


class DesignFileBody(BaseModel):
    name: str
    content: str


@router.put("/api/v4/design/file")
async def design_file_put(body: DesignFileBody) -> dict[str, Any]:
    fname = _safe_name(body.name)
    content = body.content or ""
    if len(content.encode("utf-8")) > _MAX_HTML_BYTES:
        raise HTTPException(413, "文件过大（>1.5MB）")
    _PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    p = _PREVIEW_DIR / fname
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "name": fname, "size": p.stat().st_size,
            "preview_url": f"/preview/{fname}"}


# ─── Generation ───────────────────────────────────────────────────────────────

_PROTOTYPE_SYSTEM_PROMPT = """你是 MadCop 的原型生成器，为产品经理产出可交互的 HTML 原型。

硬性要求：
1. 输出必须是**一个完整的、自包含的 HTML 文件**：从 <!DOCTYPE html> 开始到 </html> 结束，
   不要输出任何解释、markdown 代码围栏或注释性文字。
2. 所有 CSS 写在 <style> 里，所有 JS 写在 <script> 里。**零外部依赖**（不引 CDN、不引字体、不引图片外链）。
3. 移动端优先：容器 max-width:420px 居中，适配 375px 宽度视口。
4. 状态完备（PM 最容易漏的）：列表要有数据态/空态；按钮要有默认/hover/active/禁用样式；
   表单要有校验错误示例；异步内容要有 loading 占位。至少覆盖默认态和一个异常态。
5. 内容用**真实可信的中文示例数据**（真实城市名、合理的价格与日期），不要 lorem ipsum。
6. 交互用原生 JS 实现：可点击的元素必须有真实反馈（切换/展开/toast），不要纯静态。
7. 视觉规范：系统字体栈；主色 #4F46E5；圆角 8-12px；间距 8px 网格；
   正文 14px，辅助文字 12px；对比度达标。
8. 页面顶部放一个隐藏的 <!-- spec: <一句话描述> --> 注释，说明这个原型是什么。
9. **完整输出，严禁省略**：所有 CSS/JS/HTML 必须一字不落地写完整。禁止出现
   "..."、"more"、"省略"、"lots more" 或任何占位注释。哪怕代码很长也要全部写出——
   一个带省略的原型等于废品。"""


class DesignGenerateBody(BaseModel):
    prompt: str
    name: str = ""


@router.post("/api/v4/design/generate")
async def design_generate(body: DesignGenerateBody) -> dict[str, Any]:
    """Generate a prototype HTML from a natural-language prompt.

    Non-streaming on purpose: the design page shows a progress state,
    and the result lands as a file the user can then hand-edit — the
    hybrid of NL generation and manual fixes."""
    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(422, "prompt 不能为空")
    from madcop.server.routes.chat_v4 import _get_client
    client = _get_client()
    if client is None or not hasattr(client, "chat"):
        raise HTTPException(503, "没有可用的 LLM provider，请先在设置里配置")

    from madcop.llm.client import Message
    t0 = time.time()

    def _render(user_prompt: str) -> str:
        resp = client.chat(
            [Message(role="system", content=_PROTOTYPE_SYSTEM_PROMPT),
             Message(role="user", content=user_prompt)],
            model=None, temperature=0.4, max_tokens=16000,
        )
        text = (getattr(resp, "content", "") or "").strip()
        fence = re.search(r"```(?:html)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        m = re.search(r"<!DOCTYPE html[\s\S]*</html>", text, re.IGNORECASE)
        if not m:
            return ""
        html = m.group(0)
        # Laziness detection: placeholder ellipses inside code bodies mean
        # the model skipped writing the real thing (MiniMax does this).
        body = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", html)
        if re.search(r"(/\*\s*\.[\.\s]*(more|省略)?\s*\*/|<!--\s*[\.\s]*(more|省略)?\s*-->)",
                     html, re.IGNORECASE) and len(html) < 4000:
            return ""  # lazy stub — caller retries with a scolding
        return html

    html = _render(prompt)
    if not html or len(html) < 2500:
        # One scolding retry: models sometimes answer with a skeleton.
        logger.info("[design] lazy/empty output, retrying with scolding")
        try:
            html = _render(
                prompt + "\n\n（注意：上一次输出被省略或过短，被视为废品。"
                "请完整输出全部 HTML/CSS/JS，禁止任何 ... 占位。）")
        except Exception as e:
            raise HTTPException(502, f"生成失败：{e}")
    if not html:
        raise HTTPException(502, "生成结果不是有效的完整 HTML 文档，请重试或换个描述")
    elapsed = round(time.time() - t0, 1)

    # Name from the spec comment when present, else slug of the prompt.
    spec = re.search(r"<!--\s*spec:\s*(.+?)-->", html)
    base = (spec.group(1).strip() if spec else prompt)
    base = re.sub(r"[^\w\u4e00-\u9fff]+", "-", base)[:24].strip("-") or "proto"
    fname = _safe_name(f"{base}-{int(time.time()) % 100000}.html")

    _PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    (_PREVIEW_DIR / fname).write_text(html, encoding="utf-8")
    logger.info("[design] generated %s in %ss (%d bytes)",
                fname, elapsed, len(html))
    return {
        "ok": True,
        "name": fname,
        "preview_url": f"/preview/{fname}",
        "elapsed_s": elapsed,
        "bytes": len(html),
    }


__all__ = ["router"]
