#!/usr/bin/env python3
"""只阻止新增 Ruff/SAST 问题，同时保留存量问题的渐进治理空间。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
ZERO_SHA = "0" * 40
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def _commit_exists(revision: str) -> bool:
    if not revision or revision == ZERO_SHA:
        return False
    return _git("cat-file", "-e", f"{revision}^{{commit}}", check=False).returncode == 0


def resolve_base(base: str, head: str) -> str | None:
    if _commit_exists(base):
        return base
    candidate = "HEAD^" if head == "WORKTREE" else f"{head}^"
    if _commit_exists(candidate):
        return candidate
    return None


def changed_python_files(base: str | None, head: str) -> list[str]:
    if base is None:
        result = _git("ls-files", "*.py")
    elif head == "WORKTREE":
        result = _git("diff", "--name-only", "--diff-filter=ACMR", base, "--", "*.py")
    else:
        result = _git(
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{base}...{head}",
            "--",
            "*.py",
        )
    paths = set(result.stdout.splitlines())
    if head == "WORKTREE":
        untracked = _git("ls-files", "--others", "--exclude-standard", "*.py")
        paths.update(untracked.stdout.splitlines())
    return sorted(path for path in paths if path and (ROOT / path).is_file())


def added_lines(path: str, base: str | None, head: str) -> set[int] | None:
    if base is None:
        return None
    if head == "WORKTREE" and _git("ls-files", "--error-unmatch", path, check=False).returncode != 0:
        return None
    if head == "WORKTREE":
        result = _git("diff", "--unified=0", base, "--", path)
    else:
        result = _git("diff", "--unified=0", f"{base}...{head}", "--", path)
    lines: set[int] = set()
    for raw_line in result.stdout.splitlines():
        match = HUNK_RE.match(raw_line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        lines.update(range(start, start + count))
    return lines


def run_ruff(paths: Iterable[str]) -> list[dict]:
    path_list = list(paths)
    if not path_list:
        return []
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format=json", *path_list],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("Ruff 执行失败")
    return json.loads(result.stdout or "[]")


def filter_new_diagnostics(
    diagnostics: Iterable[dict],
    changed_lines: dict[str, set[int] | None],
) -> list[dict]:
    selected = []
    for diagnostic in diagnostics:
        filename = Path(diagnostic["filename"])
        try:
            relative = filename.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            relative = filename.as_posix()
        allowed_lines = changed_lines.get(relative)
        if allowed_lines is None or diagnostic["location"]["row"] in allowed_lines:
            selected.append({**diagnostic, "relative_filename": relative})
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="WORKTREE")
    args = parser.parse_args()

    base = resolve_base(args.base.strip(), args.head.strip())
    paths = changed_python_files(base, args.head)
    if not paths:
        print("本次没有新增或修改的 Python 文件。")
        return 0

    changed_lines = {path: added_lines(path, base, args.head) for path in paths}
    diagnostics = filter_new_diagnostics(run_ruff(paths), changed_lines)
    if not diagnostics:
        print(f"增量 Ruff/SAST 通过，共检查 {len(paths)} 个 Python 文件。")
        return 0

    for item in diagnostics:
        location = item["location"]
        print(
            f"{item['relative_filename']}:{location['row']}:{location['column']}: "
            f"{item['code']} {item['message']}"
        )
    print(f"发现 {len(diagnostics)} 个位于新增代码行的 Ruff/SAST 问题。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
