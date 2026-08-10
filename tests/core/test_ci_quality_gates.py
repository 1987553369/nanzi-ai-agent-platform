import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


pytestmark = pytest.mark.no_infrastructure
ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github/workflows/quality-gates.yml"


def _workflow_source() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _workflow() -> dict:
    return yaml.safe_load(_workflow_source())


def test_quality_workflow_has_bounded_triggers_permissions_and_concurrency():
    source = _workflow_source()
    workflow = _workflow()

    assert "push:" in source
    assert "pull_request:" in source
    assert "workflow_dispatch:" in source
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is True
    assert workflow["env"]["PYTHON_VERSION"] == "3.11"
    assert workflow["env"]["NODE_VERSION"] == "20.19.4"


def test_quality_workflow_covers_backend_frontend_supply_chain_and_container():
    jobs = _workflow()["jobs"]

    assert set(jobs) == {
        "backend-quality",
        "frontend-quality",
        "supply-chain",
        "container-security",
    }
    assert jobs["backend-quality"]["timeout-minutes"] == 35
    assert jobs["frontend-quality"]["timeout-minutes"] == 25
    assert jobs["supply-chain"]["timeout-minutes"] == 25
    assert jobs["container-security"]["timeout-minutes"] == 60
    assert "startsWith(github.ref, 'refs/heads/codex/')" in str(
        jobs["container-security"]["if"]
    )


def test_all_actions_use_exact_versions_or_full_commit_shas():
    refs = re.findall(r"uses:\s+[^\s@]+@([^\s#]+)", _workflow_source())

    assert refs
    assert all(
        re.fullmatch(r"(?:v?\d+\.\d+\.\d+|[0-9a-f]{40})", ref)
        for ref in refs
    )
    assert not any(ref in {"main", "master", "latest"} for ref in refs)


def test_passing_quality_gates_are_hard_failures_and_debt_is_explicit():
    jobs = _workflow()["jobs"]
    backend_steps = {step["name"]: step for step in jobs["backend-quality"]["steps"]}
    frontend_steps = {step["name"]: step for step in jobs["frontend-quality"]["steps"]}
    supply_steps = {step["name"]: step for step in jobs["supply-chain"]["steps"]}

    for name in (
        "Validate CI configuration",
        "Compile all Python sources",
        "Reject new Ruff and SAST findings",
        "Run infrastructure-free backend tests",
    ):
        assert "continue-on-error" not in backend_steps[name]
    assert backend_steps["Annotate backend test failures"]["if"] == "always()"
    assert backend_steps["Capture current mypy debt"]["continue-on-error"] is True
    assert "continue-on-error" not in frontend_steps["Run strict type check and production build"]
    assert "Pillow==11.3.0" in frontend_steps["Run frontend contract tests"]["run"]
    assert supply_steps["Generate Python dependency audit evidence"]["continue-on-error"] is True
    assert supply_steps["Generate frontend dependency audit evidence"]["continue-on-error"] is True


def test_workflow_generates_audits_sboms_and_container_scan_evidence():
    source = _workflow_source()
    supply_steps = {
        step["name"]: step for step in _workflow()["jobs"]["supply-chain"]["steps"]
    }

    for fragment in (
        "gitleaks/gitleaks-action",
        "pip-audit",
        "npm audit",
        "cyclonedx-py",
        "npm sbom",
        "python-sbom.cdx.json",
        "frontend-sbom.cdx.json",
        "docker/build-push-action",
        "aquasecurity/trivy-action",
        "trivy.sarif",
    ):
        assert fragment in source
    assert (
        supply_steps["Scan committed secrets"]["env"]["GITLEAKS_ENABLE_COMMENTS"]
        == "false"
    )


def test_python_quality_gate_includes_untracked_files_and_security_rules():
    gate = (ROOT / "scripts/ci/python_quality_gate.py").read_text(encoding="utf-8")
    ruff_config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"--others", "--exclude-standard", "*.py"' in gate
    assert '"--diff-filter=ACMR"' in gate
    assert "HUNK_RE" in gate
    assert "result.returncode == 1 and not result.stdout.strip()" in gate
    assert 'select = ["E4", "E7", "E9", "F", "S"]' in ruff_config


def test_runtime_and_development_dependencies_are_separated():
    runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    development = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    for dependency in (
        "defusedxml",
        "mypy",
        "Pillow",
        "pytest",
        "pytest-asyncio",
        "pytest-github-actions-annotate-failures",
        "pytest-mock",
        "ruff",
    ):
        assert not re.search(rf"^{dependency}(?:[<=>\[]|$)", runtime, re.MULTILINE)
        assert re.search(rf"^{dependency}==", development, re.MULTILINE)
    assert development.startswith("-r requirements.txt")


def test_docker_build_is_deterministic_and_excludes_dev_dependencies():
    dockerfile = (ROOT / "docker/Dockerfile").read_text(encoding="utf-8")
    build_helper = (ROOT / "docker/_build_common.sh").read_text(encoding="utf-8")

    assert "FROM node:20.19.4-bookworm-slim" in dockerfile
    assert "FROM python:3.11.13-slim-bookworm" in dockerfile
    assert "npm ci || npm install" not in dockerfile + build_helper
    assert "npm ci;" in dockerfile
    assert "npm ci" in build_helper
    assert 'NODE_OPTIONS="--max-old-space-size=4096"' in dockerfile
    assert "pip install --upgrade pip==25.1.1" in dockerfile
    assert "requirements-dev.txt" not in dockerfile


def test_dependabot_tracks_every_ci_dependency_ecosystem():
    config = yaml.safe_load(
        (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    )
    ecosystems = {item["package-ecosystem"] for item in config["updates"]}

    assert ecosystems == {"github-actions", "pip", "npm", "docker"}


def test_junit_collection_errors_are_emitted_as_github_annotations(tmp_path):
    report = tmp_path / "junit.xml"
    report.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite errors="1"><testcase name="tests/test_example.py">
<error message="collection failure">ImportError: missing module</error>
</testcase></testsuite></testsuites>
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci/annotate_pytest_junit.py"),
            str(report),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "::error file=tests/test_example.py,title=Pytest failure::" in result.stdout
    assert "ImportError: missing module" in result.stdout
