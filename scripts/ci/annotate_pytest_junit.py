#!/usr/bin/env python3
"""把 pytest JUnit 失败转换为 GitHub Actions 注解。"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def _escape_property(value: str) -> str:
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def _escape_message(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotations(report: Path) -> list[str]:
    root = ET.parse(report).getroot()
    output = []
    for case in root.iter("testcase"):
        problem = case.find("error")
        if problem is None:
            problem = case.find("failure")
        if problem is None:
            continue
        path = case.get("file") or case.get("name") or "pytest"
        line = case.get("line")
        properties = [f"file={_escape_property(path)}", "title=Pytest failure"]
        if line and line.isdigit():
            properties.append(f"line={line}")
        detail = (problem.text or problem.get("message") or "pytest failed").strip()
        output.append(f"::error {','.join(properties)}::{_escape_message(detail)}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    if not args.report.is_file():
        print(f"JUnit 报告不存在，跳过注解: {args.report}")
        return 0
    for annotation in annotations(args.report):
        print(annotation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
