#!/usr/bin/env python3
"""离线校验 CI 关键门禁和构建确定性。"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/quality-gates.yml"
ACTION_REF_RE = re.compile(r"uses:\s+[^\s@]+@([^\s#]+)")
EXACT_ACTION_VERSION_RE = re.compile(r"^(?:v?\d+\.\d+\.\d+|[0-9a-f]{40})$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    workflow_source = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(workflow_source)
    require(isinstance(parsed, dict) and "jobs" in parsed, "CI workflow 不是有效的 GitHub Actions YAML")

    refs = ACTION_REF_RE.findall(workflow_source)
    require(refs, "CI workflow 未使用任何可审计 Action")
    for ref in refs:
        require(
            bool(EXACT_ACTION_VERSION_RE.fullmatch(ref)),
            f"Action 必须固定到完整提交 SHA 或精确语义版本，当前为: {ref}",
        )

    required_fragments = (
        "python_quality_gate.py",
        "compileall",
        "-m no_infrastructure",
        "npm ci",
        "npm run build",
        "gitleaks/gitleaks-action",
        "pip-audit",
        "npm audit",
        "cyclonedx-py",
        "npm sbom",
        "docker/build-push-action",
        "aquasecurity/trivy-action",
    )
    for fragment in required_fragments:
        require(fragment in workflow_source, f"CI workflow 缺少门禁: {fragment}")

    dockerfile = (ROOT / "docker/Dockerfile").read_text(encoding="utf-8")
    build_helper = (ROOT / "docker/_build_common.sh").read_text(encoding="utf-8")
    deterministic_build_sources = dockerfile + build_helper
    require(
        "npm ci || npm install" not in deterministic_build_sources,
        "Docker 构建及宿主机预构建禁止回退到非确定性的 npm install",
    )
    require("npm ci;" in dockerfile, "Docker 前端依赖必须使用 npm ci")
    require("npm ci" in build_helper, "宿主机前端预构建必须使用 npm ci")
    require("requirements-dev.txt" not in dockerfile, "生产镜像不得安装开发依赖")

    runtime_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for dev_dependency in ("pytest", "pytest-asyncio", "pytest-mock", "mypy", "ruff"):
        require(
            not re.search(rf"^{re.escape(dev_dependency)}(?:[<=>\[]|$)", runtime_requirements, re.MULTILINE),
            f"运行时依赖中仍包含开发工具: {dev_dependency}",
        )

    print("CI 配置、Action 版本和构建确定性检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
