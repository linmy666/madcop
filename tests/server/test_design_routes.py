"""Design workshop routes — hybrid PM prototype tool.

The critical contract: _safe_name must never mangle the .html
extension (the 61518_html.html bug) and must never escape the
preview directory.
"""
from __future__ import annotations

from madcop.server.routes.design_routes import _safe_name


def test_safe_name_preserves_extension():
    assert _safe_name('外卖-61518_html.html') == '外卖-61518_html.html'
    assert _safe_name('proto.html') == 'proto.html'
    assert _safe_name('proto') == 'proto.html'


def test_safe_name_strips_paths_and_bad_chars():
    assert _safe_name('../../etc/passwd.html') == 'passwd.html'
    assert _safe_name('a b/c d.html') == 'c_d.html'
    assert _safe_name('') == 'untitled.html'


def test_safe_name_handles_backslash_and_double_ext():
    assert _safe_name('a\\b.html') == 'b.html'
    assert _safe_name('x.HTML') == 'x.HTML'.replace('.HTML', '') + '.html'
