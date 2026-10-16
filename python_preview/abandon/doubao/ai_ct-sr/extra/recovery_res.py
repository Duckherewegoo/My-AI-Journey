#!/usr/bin/env python3
"""
批量从 __pycache__/*.pyc 恢复源码。

用法:
    python recover_sources.py --root /path/to/project --output ./recovered
    python recover_sources.py --root . --output ./recovered --tools xdis

工具策略（按优先级）:
    1. pycdc  —— 真正的反编译，输出可读 .py（需手动安装）
    2. xdis   —— 跨版本反汇编，输出 .dis（pip install xdis）
    3. dis    —— 内置反汇编，仅当 pyc 版本 == 当前 Python 版本时可用

输出结构: 保持原项目的相对路径，例如
    recovered/nova/ablation/model.dis
    recovered/nova/ablation/model.py      # 如果 pycdc 可用
"""

import argparse
import dis
import importlib.util
import io
import marshal
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

# ---------- 工具检测 ----------
def tool_available(name: str) -> bool:
    return shutil.which(name) is not None

HAS_PYCDC = tool_available("pycdc")

try:
    import xdis
    from xdis import disassemble_file as xdis_disassemble
    HAS_XDIS = True
except ImportError:
    HAS_XDIS = False


# ---------- 核心: 从 pyc 路径推导原始 py 路径 ----------
def pyc_to_module_path(pyc_path: Path, root: Path) -> Path:
    """
    project/nova/ablation/__pycache__/model.cpython-310.pyc
    → nova/ablation/model       （相对 root 的模块路径，无后缀）
    """
    # pyc 的父目录是 __pycache__，再往上是模块所在目录
    module_dir = pyc_path.parent.parent
    rel_dir = module_dir.relative_to(root)

    stem = pyc_path.stem
    # 去掉 .cpython-310 / .cpython-311 / .pypy310 之类后缀
    if "." in stem:
        base, maybe_impl = stem.rsplit(".", 1)
        if maybe_impl.startswith(("cpython", "pypy")):
            stem = base

    return rel_dir / stem


# ---------- 策略 1: pycdc ----------
def decompile_pycdc(pyc_path: Path, out_py: Path) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["pycdc", str(pyc_path)],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, "超时"

    if r.returncode == 0 and r.stdout.strip():
        out_py.parent.mkdir(parents=True, exist_ok=True)
        out_py.write_text(
            f"# 反编译源文件: {pyc_path}\n"
            f"# 生成时间: {datetime.now()}\n"
            f"# {'=' * 76}\n\n" + r.stdout,
            encoding="utf-8",
        )
        return True, "pycdc"
    return False, f"pycdc 返回码 {r.returncode}: {r.stderr[:120]}"


# ---------- 策略 2: xdis 反汇编 ----------
def disassemble_xdis(pyc_path: Path, out_dis: Path) -> tuple[bool, str]:
    try:
        out_dis.parent.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        buf.write(f"# 反汇编源文件: {pyc_path}\n")
        buf.write(f"# 生成时间: {datetime.now()}\n")
        buf.write("# " + "=" * 76 + "\n\n")

        # xdis 会把反汇编写到 outstream（需是打开的文件对象或 StringIO）
        xdis_disassemble(str(pyc_path), buf)

        out_dis.write_text(buf.getvalue(), encoding="utf-8")
        return True, "xdis"
    except Exception as e:
        return False, f"xdis 失败: {e}"


# ---------- 策略 3: 内置 dis ----------
def disassemble_dis(pyc_path: Path, out_dis: Path) -> tuple[bool, str]:
    try:
        with open(pyc_path, "rb") as f:
            magic = f.read(4)
            # 跳过其余头部（不同 Python 版本头部长度不同，试 16 字节）
            f.seek(16)
            code = marshal.load(f)

        out_dis.parent.mkdir(parents=True, exist_ok=True)
        with open(out_dis, "w", encoding="utf-8") as out:
            out.write(f"# 反汇编源文件: {pyc_path}\n")
            out.write(f"# 生成时间: {datetime.now()}\n")
            out.write("# " + "=" * 76 + "\n\n")
            dis.dis(code, file=out)
        return True, "dis"
    except Exception as e:
        return False, f"dis 失败: {e}"


# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="项目根目录")
    ap.add_argument("--output", required=True, help="输出目录")
    ap.add_argument(
        "--tools", default="auto",
        help="auto | pycdc | xdis | dis （默认 auto）"
    )
    ap.add_argument(
        "--no-dis", action="store_true",
        help="禁止回退到 dis（推荐，避免无意义的失败）"
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_root = Path(args.output).resolve()

    if not root.is_dir():
        print(f"❌ root 不存在: {root}")
        sys.exit(1)

    out_root.mkdir(parents=True, exist_ok=True)

    # 找所有 .pyc
    pyc_files = sorted(root.rglob("__pycache__/*.pyc"))
    print(f"🔍 在 {root} 下找到 {len(pyc_files)} 个 .pyc 文件")
    print(f"🔧 可用工具: pycdc={HAS_PYCDC}, xdis={HAS_XDIS}, dis=内置")
    print(f"📁 输出目录: {out_root}\n")

    stats = {"ok": 0, "fail": 0, "skip": 0}
    fail_list = []

    for i, pyc in enumerate(pyc_files, 1):
        rel = pyc.relative_to(root)
        mod = pyc_to_module_path(pyc, root)
        out_base = out_root / mod

        print(f"[{i:3d}/{len(pyc_files)}] {rel}")

        success = False
        used = None
        msg = "无可用工具（请安装 xdis 或 pycdc）"   # ← 加这一行
        # 按优先级尝试
        if not success and HAS_PYCDC and args.tools in ("auto", "pycdc"):
            ok, msg = decompile_pycdc(pyc, out_base.with_suffix(".py"))
            if ok:
                success, used = True, msg

        if not success and HAS_XDIS and args.tools in ("auto", "xdis"):
            ok, msg = disassemble_xdis(pyc, out_base.with_suffix(".dis"))
            if ok:
                success, used = True, msg

        if not success and not args.no_dis and args.tools in ("auto", "dis"):
            ok, msg = disassemble_dis(pyc, out_base.with_suffix(".dis"))
            if ok:
                success, used = True, msg

        if success:
            print(f"      ✅ 用 {used}")
            stats["ok"] += 1
        else:
            print(f"      ❌ 全部失败: {msg}")
            stats["fail"] += 1
            fail_list.append((str(rel), msg))

    # 汇总报告
    report = out_root / "_RECOVERY_REPORT.txt"
    report.write_text(
        f"恢复报告\n"
        f"{'=' * 60}\n"
        f"项目根目录: {root}\n"
        f"输出目录:   {out_root}\n"
        f"扫描时间:   {datetime.now()}\n"
        f"pyc 总数:   {len(pyc_files)}\n"
        f"成功:       {stats['ok']}\n"
        f"失败:       {stats['fail']}\n"
        f"跳过:       {stats['skip']}\n"
        f"工具状态:   pycdc={HAS_PYCDC}, xdis={HAS_XDIS}\n"
        f"\n失败清单:\n" +
        ("\n".join(f"  - {p}\n      原因: {r}" for p, r in fail_list) or "  (无)"),
        encoding="utf-8",
    )

    print(f"\n{'=' * 60}")
    print(f"✅ 成功: {stats['ok']}")
    print(f"❌ 失败: {stats['fail']}")
    print(f"📄 报告: {report}")


if __name__ == "__main__":
    main()
