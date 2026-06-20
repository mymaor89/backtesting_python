"""
Tests for the FastAPI backtest microservice.

The validation/CORS/health paths are hermetic. The happy-path run needs the local
TimescaleDB; it is skipped automatically when the DB is unreachable so the suite
stays green in environments without it.
"""
import psycopg2
import pytest
from fastapi.testclient import TestClient

from api_server import app
import run_5s_replay

client = TestClient(app)


def _db_available() -> bool:
    try:
        run_5s_replay.fetch_5s("MNQM6", "2026-06-10", "2026-06-10")
        return True
    except Exception:
        return False


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "ema_retest_v134" in r.json()["strategies"]
    assert "ema_crossover" in r.json()["strategies"]


def test_unknown_strategy_is_422():
    r = client.post("/api/v1/backtest/run", json={"strategy_name": "nope"})
    assert r.status_code == 422
    assert "unknown strategy" in r.json()["detail"]


def test_cors_preflight_allows_lan_origins():
    # Default config allows all origins (trusted LAN), so any device on the
    # network — e.g. http://192.168.1.190:5173 — gets a permissive preflight.
    for origin in ("http://localhost:5173", "http://192.168.1.190:5173",
                   "http://192.168.1.234:5173"):
        r = client.options(
            "/api/v1/backtest/run",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == "*"


def test_run_returns_metrics_and_trades_without_db(monkeypatch):
    """Endpoint shape is asserted with the heavy run stubbed out (no DB needed).
    Also asserts the request's `parameters` are forwarded to run_replay."""
    seen = {}
    fake = {
        "strategy_name": "ema_crossover", "symbol": "MNQM6",
        "start": "2026-06-10", "end": "2026-06-11",
        "applied_params": {"take_profit_points": 25.0},
        "ignored_params": ["session"],
        "metrics": {
            "total_pnl": 300.0, "optimistic_pnl": 300.0, "optimism_gap": 0.0,
            "trades_count": 2, "wins": 2, "losses": 0, "win_rate": 1.0,
            "tp_fills": 2, "sl_fills": 0, "buffer_breaches": 0,
            "bar_close_rescues": 0, "sub_bars_5s": 100, "strategy_bars_1m": 10,
        },
        "trades": [{
            "entry_time": "2026-06-10T10:00:00-04:00", "side": "LONG",
            "entry_price": 100.0, "qty": 2, "exit_time": "2026-06-10T10:01:00-04:00",
            "exit_price": 110.0, "exits": ["TP"], "realized_pnl": 40.0,
            "breach": False, "rescue": False,
        }],
    }

    def _capture(**kw):
        seen.update(kw)
        return fake

    monkeypatch.setattr("api_server.run_replay", _capture)
    r = client.post("/api/v1/backtest/run",
                    json={"strategy_name": "ema_crossover",
                          "parameters": {"take_profit_points": 25, "session": {}}})
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"]["trades_count"] == 2
    assert body["trades"][0]["side"] == "LONG"
    assert body["applied_params"] == {"take_profit_points": 25.0}
    assert body["ignored_params"] == ["session"]
    # the request parameters reached run_replay
    assert seen["parameters"] == {"take_profit_points": 25, "session": {}}


def test_param_translation_maps_and_restores():
    """_apply_version_params remaps live-schema keys → replay globals, reports
    unknown keys as ignored, and restore() puts the globals back."""
    import shared_strategies.ema_retest_v134 as m
    from run_5s_replay import _apply_version_params

    before_tp, before_dist = m.TP_PTS, m.MIN_EMA_DISTANCE
    applied, ignored, restore = _apply_version_params(
        {"take_profit_points": 25, "ema_distance_min_points": 5,
         "session": {}, "ema_distance_max_points": 75})
    try:
        assert m.TP_PTS == 25.0 and m.MIN_EMA_DISTANCE == 5.0
        assert applied == {"take_profit_points": 25.0, "ema_distance_min_points": 5.0}
        assert set(ignored) == {"session", "ema_distance_max_points"}
    finally:
        restore()
    assert m.TP_PTS == before_tp and m.MIN_EMA_DISTANCE == before_dist


@pytest.mark.skipif(not _db_available(), reason="TimescaleDB not reachable")
def test_run_happy_path_against_db():
    r = client.post("/api/v1/backtest/run", json={
        "strategy_name": "ema_retest_v134",
        "start_time": "2026-06-10", "end_time": "2026-06-12",
    })
    assert r.status_code == 200
    m = r.json()["metrics"]
    assert m["trades_count"] >= 1
    assert isinstance(m["total_pnl"], (int, float))
    assert len(r.json()["trades"]) == m["trades_count"]
