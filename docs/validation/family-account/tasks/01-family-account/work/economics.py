"""Break-even scenarios for the family account (task 01-family-account).

All inputs are hypotheses (E21-E25) to be replaced with data of operator N.
Model: the function lowers monthly churn of grouped subscribers by delta.
Retained subscribers grow linearly, so the cumulative margin over a horizon
of H months is margin * N * delta * H^2 / 2. Break-even: this equals cost.

Run: python work/economics.py
"""
from __future__ import annotations

from dataclasses import dataclass

HORIZON_MONTHS = 24  # evaluation horizon, months


@dataclass(frozen=True)
class Scenario:
    """One set of input hypotheses."""

    name: str
    subscribers: float  # N in groups by end of year 1 (E21)
    margin: float  # margin per subscriber per month, rubles (E22)
    cost: float  # build + one year of support, rubles (E23)
    churn: float  # baseline monthly churn of these subscribers (E24)
    prevent: float  # share of related churn the function prevents (E25)


SCENARIOS = (
    Scenario("осторожный", 100_000, 150, 80e6, 0.015, 0.20),
    Scenario("базовый", 300_000, 250, 40e6, 0.020, 0.30),
    Scenario("смелый", 1_000_000, 400, 20e6, 0.025, 0.40),
)


def breakeven_delta(s: Scenario, horizon: int = HORIZON_MONTHS) -> float:
    """Return the monthly churn reduction (fraction) needed to repay the cost."""
    return 2 * s.cost / (s.margin * s.subscribers * horizon**2)


def required_share(s: Scenario) -> float:
    """Return the share of churn that must be tied to the missing function.

    The relative reduction r = delta / churn must be produced by the
    function, which prevents only a part of the related churn:
    share * prevent >= r.
    """
    return breakeven_delta(s) / s.churn / s.prevent


def main() -> None:
    """Print the three scenarios."""
    print(f"Горизонт: {HORIZON_MONTHS} мес.")
    for s in SCENARIOS:
        d = breakeven_delta(s)
        rel = d / s.churn
        share = required_share(s)
        verdict = "не сходится (нужно больше всего оттока)" if share > 1 else "возможно"
        print(
            f"{s.name}: снижение оттока для окупаемости {d * 100:.3f} п.п. в мес."
            f" ({rel * 100:.1f}% от базового оттока); связанная с функцией доля"
            f" уходов должна быть не ниже {min(share, 9.99) * 100:.0f}% -> {verdict}"
        )


if __name__ == "__main__":
    main()
