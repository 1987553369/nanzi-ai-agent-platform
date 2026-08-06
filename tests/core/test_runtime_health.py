from pathlib import Path

import pytest

from app.core.runtime_health import RuntimeHealthState


ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.no_infrastructure


def test_runtime_health_tracks_startup_and_drain_transitions():
    state = RuntimeHealthState()

    state.begin_startup()
    assert state.ready_for_traffic is False

    state.finish_startup()
    assert state.ready_for_traffic is True

    state.begin_draining()
    assert state.ready_for_traffic is False

    state.finish_shutdown()
    assert state.startup_complete is False


def test_main_exposes_distinct_orchestration_probes():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")

    assert '@app.get("/live")' in source
    assert '@app.get("/startup")' in source
    assert '@app.get("/ready")' in source
    assert 'text("SELECT 1")' in source
    assert "redis.redis_client.ping()" in source
    assert "runtime_health.begin_draining()" in source
