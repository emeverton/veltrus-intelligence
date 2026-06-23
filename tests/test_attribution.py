from datetime import datetime, timedelta, timezone

import pytest

from src.attribution.models_math import (
    Touchpoint,
    first_touch,
    last_touch,
    linear,
    run_all_sync_models,
    shapley,
    time_decay,
)

NOW = datetime.now(timezone.utc)


def make_tp(channel: str, days_ago: float) -> Touchpoint:
    return Touchpoint(
        channel=channel,
        campaign_id=None,
        occurred_at=NOW - timedelta(days=days_ago),
    )


def test_first_touch_single():
    tps = [make_tp("google_ads", 5), make_tp("meta_ads", 2)]
    result = first_touch(tps)
    assert result == {"google_ads": 1.0}


def test_last_touch_single():
    tps = [make_tp("google_ads", 5), make_tp("meta_ads", 2)]
    result = last_touch(tps)
    assert result == {"meta_ads": 1.0}


def test_linear_equal():
    tps = [make_tp("google_ads", 5), make_tp("meta_ads", 3), make_tp("email", 1)]
    result = linear(tps)
    assert abs(result["google_ads"] - 1 / 3) < 1e-6
    assert abs(result["meta_ads"] - 1 / 3) < 1e-6
    assert abs(result["email"] - 1 / 3) < 1e-6


def test_time_decay_recent_gets_more():
    tps = [make_tp("google_ads", 14), make_tp("meta_ads", 1)]
    result = time_decay(tps, NOW, half_life_days=7.0)
    assert result["meta_ads"] > result["google_ads"]
    assert abs(sum(result.values()) - 1.0) < 1e-6


def test_shapley_single_channel():
    tps = [make_tp("google_ads", 3), make_tp("google_ads", 1)]
    result = shapley(tps)
    assert result == {"google_ads": 1.0}


def test_shapley_two_channels_sum_one():
    tps = [make_tp("google_ads", 5), make_tp("meta_ads", 2)]
    result = shapley(tps)
    assert abs(sum(result.values()) - 1.0) < 1e-6


def test_run_all_sync_models_returns_four():
    tps = [make_tp("google_ads", 5), make_tp("meta_ads", 2)]
    result = run_all_sync_models(tps, NOW)
    assert set(result.keys()) == {"first_touch", "last_touch", "linear", "time_decay"}


def test_empty_touchpoints():
    assert first_touch([]) == {}
    assert last_touch([]) == {}
    assert linear([]) == {}
    assert time_decay([], NOW) == {}
    assert shapley([]) == {}
