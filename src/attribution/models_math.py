from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import permutations
import random


@dataclass
class Touchpoint:
    channel: str
    campaign_id: str | None
    occurred_at: datetime


def first_touch(touchpoints: list[Touchpoint]) -> dict[str, float]:
    if not touchpoints:
        return {}
    first = min(touchpoints, key=lambda t: t.occurred_at)
    return {first.channel: 1.0}


def last_touch(touchpoints: list[Touchpoint]) -> dict[str, float]:
    if not touchpoints:
        return {}
    last = max(touchpoints, key=lambda t: t.occurred_at)
    return {last.channel: 1.0}


def linear(touchpoints: list[Touchpoint]) -> dict[str, float]:
    if not touchpoints:
        return {}
    credit_per = 1.0 / len(touchpoints)
    result: dict[str, float] = {}
    for t in touchpoints:
        result[t.channel] = result.get(t.channel, 0.0) + credit_per
    return result


def time_decay(
    touchpoints: list[Touchpoint],
    conversion_time: datetime,
    half_life_days: float = 7.0,
) -> dict[str, float]:
    if not touchpoints:
        return {}
    weights: dict[str, float] = {}
    for t in touchpoints:
        days_before = (conversion_time - t.occurred_at).total_seconds() / 86400.0
        weight = 2.0 ** (-days_before / half_life_days)
        weights[t.channel] = weights.get(t.channel, 0.0) + weight
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def shapley(touchpoints: list[Touchpoint]) -> dict[str, float]:
    channels = list({t.channel for t in touchpoints})
    n = len(channels)

    if n == 0:
        return {}
    if n == 1:
        return {channels[0]: 1.0}
    if n > 8:
        return _shapley_monte_carlo(channels, n_samples=10_000)

    shapley_values: dict[str, float] = {c: 0.0 for c in channels}
    all_perms = list(permutations(channels))
    n_perms = len(all_perms)

    for perm in all_perms:
        for i, channel in enumerate(perm):
            coalition = set(perm[:i])
            coalition_with = coalition | {channel}
            v_with = len(coalition_with) / n
            v_without = len(coalition) / n
            shapley_values[channel] += (v_with - v_without) / n_perms

    total = sum(shapley_values.values())
    if total == 0:
        return {c: 1.0 / n for c in channels}
    return {k: v / total for k, v in shapley_values.items()}


def _shapley_monte_carlo(channels: list[str], n_samples: int = 10_000) -> dict[str, float]:
    n = len(channels)
    values: dict[str, float] = {c: 0.0 for c in channels}

    for _ in range(n_samples):
        perm = channels[:]
        random.shuffle(perm)
        for i, channel in enumerate(perm):
            coalition_size = i
            coalition_with_size = i + 1
            v_with = coalition_with_size / n
            v_without = coalition_size / n
            values[channel] += (v_with - v_without)

    total = sum(values.values())
    return {k: v / total for k, v in values.items()} if total > 0 else {c: 1.0 / n for c in channels}


def run_all_sync_models(
    touchpoints: list[Touchpoint],
    conversion_time: datetime,
) -> dict[str, dict[str, float]]:
    return {
        "first_touch": first_touch(touchpoints),
        "last_touch": last_touch(touchpoints),
        "linear": linear(touchpoints),
        "time_decay": time_decay(touchpoints, conversion_time),
    }
