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
REQUIREMENT_NAME_RE = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[.*?\])?(?:[<>=!~].*)?$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def direct_requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = REQUIREMENT_NAME_RE.fullmatch(line)
        if match is None:
            raise ValueError(f"无法解析依赖声明: {path.name}: {line}")
        normalized = match.group(1).lower().replace("_", "-")
        require(normalized not in names, f"依赖在 {path.name} 内重复声明: {normalized}")
        names.add(normalized)
    return names


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
        "annotate_pytest_junit.py",
        "compileall",
        "-m no_infrastructure",
        "npm ci",
        "Pillow==11.3.0",
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

    aggregate_source = (ROOT / "requirements.in").read_text(encoding="utf-8")
    aggregate_lines = {
        line.split("#", 1)[0].strip()
        for line in aggregate_source.splitlines()
        if line.split("#", 1)[0].strip()
    }
    require(
        aggregate_lines == {"-r requirements-core.in", "-r requirements-optional.in"},
        "requirements.in 必须只聚合 core 与 optional 源清单",
    )
    core_names = direct_requirement_names(ROOT / "requirements-core.in")
    optional_names = direct_requirement_names(ROOT / "requirements-optional.in")
    require(bool(core_names), "核心依赖源清单不能为空")
    require(bool(optional_names), "可选依赖源清单不能为空")
    require(
        core_names.isdisjoint(optional_names),
        f"核心与可选依赖重复声明: {sorted(core_names & optional_names)}",
    )
    development_source = (ROOT / "requirements-dev.in").read_text(encoding="utf-8")
    require(
        "-r requirements.in" in development_source.splitlines(),
        "开发依赖源清单必须继承完整生产依赖源清单",
    )

    runtime_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for dev_dependency in (
        "defusedxml",
        "pytest",
        "pytest-asyncio",
        "pytest-github-actions-annotate-failures",
        "pytest-mock",
        "mypy",
        "ruff",
    ):
        require(
            not re.search(rf"^{re.escape(dev_dependency)}(?:[<=>\[]|$)", runtime_requirements, re.MULTILINE),
            f"运行时依赖中仍包含开发工具: {dev_dependency}",
        )

    print("CI 配置、依赖分组、Action 版本和构建确定性检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
