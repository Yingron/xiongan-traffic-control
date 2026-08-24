"""Remove obsolete SUMO program 0 definitions from the formal 30-junction net.

The DQN and visualisation pipelines use the explicit four-phase ``rl4`` program
for every J01--J30 signal.  Older netconvert output also retained a same-ID
``programID=\"0\"`` baseline program, whose phase 1/3 are yellow transitions;
leaving both programs makes SUMO's default selection ambiguous.

Usage:
    python scripts/clean_sumo_tl_programs.py --check
    python scripts/clean_sumo_tl_programs.py --write
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NET_PATH = REPO_ROOT / "sumo_files" / "xiongan_30.net.xml"
EXPECTED_IDS = {f"J{index:02d}" for index in range(1, 31)}
TL_LOGIC_PATTERN = re.compile(
    r"\s*<tlLogic id=\"(?P<id>J\d{2})\"[^>]*\bprogramID=\"(?P<program>[^\"]+)\"[^>]*>.*?</tlLogic>",
    re.DOTALL,
)


def inspect(text: str) -> Counter:
    """Return per-program counts and reject an incomplete 30-junction net."""
    entries = [match.groupdict() for match in TL_LOGIC_PATTERN.finditer(text)]
    ids = {entry["id"] for entry in entries}
    if ids != EXPECTED_IDS:
        missing = sorted(EXPECTED_IDS - ids)
        extra = sorted(ids - EXPECTED_IDS)
        raise ValueError(f"tlLogic 路口集合异常；missing={missing}, extra={extra}")
    return Counter(entry["program"] for entry in entries)


def remove_program_zero(text: str) -> tuple[str, list[str]]:
    """Drop only J01--J30's legacy program 0 blocks, retaining exact XML layout."""
    removed: list[str] = []

    def replace(match: re.Match) -> str:
        if match.group("program") != "0":
            return match.group(0)
        removed.append(match.group("id"))
        return ""

    cleaned = TL_LOGIC_PATTERN.sub(replace, text)
    if set(removed) != EXPECTED_IDS or len(removed) != 30:
        raise ValueError(f"预期移除 30 个 program 0，实际移除 {len(removed)} 个：{sorted(removed)}")
    return cleaned, removed


def main() -> None:
    parser = argparse.ArgumentParser(description="清理 xiongan_30.net.xml 的冗余 program 0")
    parser.add_argument("--write", action="store_true", help="通过校验后原地写入正式 net.xml")
    parser.add_argument("--check", action="store_true", help="只检查，不修改文件")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("请且仅使用 --check 或 --write")

    source = NET_PATH.read_text(encoding="utf-8")
    before = inspect(source)
    print(f"清理前 tlLogic 程序统计: {dict(before)}")

    if args.check:
        if before == Counter({"rl4": 30}):
            print("[OK] 正式路网已仅保留 J01--J30 的 rl4 程序。")
            return
        if before == Counter({"rl4": 30, "0": 30}):
            print("[NEEDS-CLEAN] 发现 30 个冗余 program 0；执行 --write 可清理。")
            return
        raise ValueError(f"未知 tlLogic 程序组合: {dict(before)}")

    if before != Counter({"rl4": 30, "0": 30}):
        raise ValueError(f"拒绝覆盖未知 tlLogic 程序组合: {dict(before)}")
    cleaned, removed = remove_program_zero(source)
    after = inspect(cleaned)
    if after != Counter({"rl4": 30}):
        raise ValueError(f"清理后程序统计异常: {dict(after)}")
    NET_PATH.write_text(cleaned, encoding="utf-8")
    print(f"[OK] 已移除 {len(removed)} 个 program 0；清理后统计: {dict(after)}")


if __name__ == "__main__":
    main()
