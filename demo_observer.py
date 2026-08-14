#!/usr/bin/env python3
"""
MadCop Observer Demo — 快速演示后台监控 + 异常提醒

用法:
  python3 demo_observer.py

这个脚本会:
  1. 创建一个临时项目目录
  2. 写入一个正常的 Python 文件
  3. 等 2 秒后，修改成有 SyntaxError 的版本（模拟保存了有 bug 的代码）
  4. 等观察器检测到并提醒

前提: MadCop 桌面端已打开, 观察器已开启, workspace 已设到这个目录
"""
import time
import os
from pathlib import Path

DEMO_DIR = Path.home() / "madcop_demo_workspace"

def main():
    DEMO_DIR.mkdir(exist_ok=True)
    demo_file = DEMO_DIR / "app.py"

    print(f"📁 Demo workspace: {DEMO_DIR}")
    print(f"📄 Demo file: {demo_file}")
    print()

    # Step 1: 写正常代码
    print("1️⃣  写入正常代码...")
    demo_file.write_text('''def calculate_total(items):
    """Calculate total price of items."""
    return sum(item["price"] for item in items)

print(calculate_total([{"price": 10}, {"price": 20}]))
''')
    print("   ✓ 正常代码已保存（观察器不会提醒）")
    print()

    # Step 2: 等 3 秒
    print("2️⃣  等待 3 秒...")
    time.sleep(3)

    # Step 3: 写有 bug 的代码（SyntaxError）
    print("3️⃣  写入有 SyntaxError 的代码...")
    demo_file.write_text('''def calculate_total(items:
    """Missing closing parenthesis — SyntaxError!"""
    return sum(item["price"] for item in items

# Traceback (most recent call last):
#   File "app.py", line 1
#     def calculate_total(items:
#                          ^
# SyntaxError: invalid syntax
print(calculate_total([{"price": 10}, {"price": 20}]))
''')
    print("   ⚠ 有 bug 的代码已保存！")
    print("   观察器应该检测到 SyntaxError 并发出提醒...")
    print()

    # Step 4: 等待观察器响应
    print("4️⃣  等待观察器响应（最多 15 秒）...")
    for i in range(15):
        time.sleep(1)
        print(f"   等待中... {i+1}s")
    print()
    print("✅ 如果你在 MadCop 里看到了通知/toast，说明观察器正常工作！")
    print(f"   清理: rm -rf {DEMO_DIR}")


if __name__ == "__main__":
    main()
