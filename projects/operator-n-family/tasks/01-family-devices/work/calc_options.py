"""Option comparison arithmetic for task 01-family-devices (after critic pass).

Inputs: brief facts (E-numbers) and labelled assumptions. Run:
    python projects/operator-n-family/tasks/01-family-devices/work/calc_options.py
"""

import random
from datetime import date, timedelta
from math import ceil, erf, log, sqrt

Z_ALPHA = 1.96  # two-sided 5 %
Z_BETA = 0.8416  # power 80 %
GP_PER_PAID_MONTH_RUB = 500  # E9
GROUPS_BASE = 6_500  # E6
ACCESSIBLE_OWNERS = 40_000  # E1


def n_per_arm(p_control: float, p_treat: float) -> int:
    """Groups per arm to detect a difference of two proportions.

    Args:
        p_control: restriction share under usual service.
        p_treat: restriction share with the signal.

    Returns:
        Required groups in each arm.
    """
    p_bar = (p_control + p_treat) / 2
    num = (Z_ALPHA * sqrt(2 * p_bar * (1 - p_bar))
           + Z_BETA * sqrt(p_control * (1 - p_control) + p_treat * (1 - p_treat))) ** 2
    return ceil(num / (p_control - p_treat) ** 2)


def eligible_weekly_flow(groups: float, monthly_low: float, eligible_share: float) -> float:
    """Eligible low-balance group-months per week (NOT distinct groups).

    The same group can hit low balance again next month and is counted
    again, so this is an event flow (audit item 8). Distinct first-time
    groups come from ``unique_first_groups``.

    Args:
        groups: connected groups.
        monthly_low: share of groups with a low-balance event per month (E33).
        eligible_share: share passing tariff, permission and free-balance filters.

    Returns:
        Eligible group-months per week.
    """
    return groups * monthly_low * eligible_share * 12 / 52


def unique_first_groups(groups: float, monthly_low: float, eligible_share: float,
                        weeks: float) -> float:
    """Distinct groups with a first eligible event within ``weeks``.

    Illustration only: eligibility is a fixed subset of groups and months
    are independent with the same monthly probability (no data yet).

    Args:
        groups: connected groups.
        monthly_low: monthly probability of a low-balance event (E33).
        eligible_share: fixed share of groups that pass the filters.
        weeks: recruitment window from pilot start.

    Returns:
        Distinct first-time eligible groups.
    """
    months = weeks * 12 / 52
    return groups * eligible_share * (1 - (1 - monthly_low) ** months)


def weeks_to_recruit(groups: float, monthly_low: float, eligible_share: float,
                     needed: float) -> float | None:
    """Weeks until ``needed`` distinct groups have had a first event.

    Args:
        groups: connected groups.
        monthly_low: monthly probability of a low-balance event (E33).
        eligible_share: fixed share of groups that pass the filters.
        needed: groups required for the pilot (E38).

    Returns:
        Weeks, or None if the eligible pool is smaller than ``needed``.
    """
    pool = groups * eligible_share
    if pool <= needed:
        return None
    months = log(1 - needed / pool) / log(1 - monthly_low)
    return months * 52 / 12


PILOT_START = date(2027, 6, 1)
OBSERVATION_DAYS = 7


def result_date_first_events(groups: float, monthly_low: float, eligible_share: float,
                             needed: float) -> date | None:
    """Earliest result date under the first-event model, full days (audit-2 item 2).

    Args:
        groups: connected groups at pilot start.
        monthly_low: monthly probability of a low-balance event (E33).
        eligible_share: fixed share of groups that pass the filters.
        needed: groups required for the pilot (E38).

    Returns:
        Date the last recruited group finishes observation, or None if the pool is too small.
    """
    w = weeks_to_recruit(groups, monthly_low, eligible_share, needed)
    if w is None:
        return None
    return PILOT_START + timedelta(days=ceil(w * 7) + OBSERVATION_DAYS)


def overall_false_positive(n1: int, n2: int, p: float, z1: float, z2: float,
                           threshold_pp: float = 5.0, draws: int = 400_000,
                           seed: int = 7) -> dict[str, float]:
    """Error of the whole two-look plan under a true zero effect (audit-2 item 5).

    Look 1 at n1 per arm with critical value z1. If its CI covers both 0 and
    the threshold, n2 more groups per arm are added and the pooled estimate
    is tested with z2. Error = the plan ends with a CI wholly above zero.
    Monte Carlo with a fixed seed, normal approximation.

    Args:
        n1: groups per arm at look 1.
        n2: extra groups per arm in the extension.
        p: restriction share in both arms (null).
        z1: critical value at look 1.
        z2: critical value at the final look.
        threshold_pp: extension threshold, p.p.
        draws: Monte Carlo draws.
        seed: random seed.

    Returns:
        One-sided error at look 1, after extension, total, and share extended.
    """
    rng = random.Random(seed)
    sd1 = sqrt(2 * p * (1 - p) / n1) * 100
    sd2 = sqrt(2 * p * (1 - p) / n2) * 100
    sdf = sqrt(2 * p * (1 - p) / (n1 + n2)) * 100
    err1 = err2 = ext = 0
    for _ in range(draws):
        d1 = rng.gauss(0.0, sd1)
        if d1 - z1 * sd1 > 0:
            err1 += 1
            continue
        if d1 - z1 * sd1 <= 0 <= threshold_pp <= d1 + z1 * sd1:
            ext += 1
            d = (n1 * d1 + n2 * rng.gauss(0.0, sd2)) / (n1 + n2)
            if d - z2 * sdf > 0:
                err2 += 1
    return {"look1": err1 / draws, "after_extension": err2 / draws,
            "total": (err1 + err2) / draws, "extended": ext / draws}


def norm_cdf(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1 + erf(x / sqrt(2)))


def decision_probabilities(n_arm: int, p_control: float, effect_pp: float,
                           threshold_pp: float = 5.0) -> dict[str, float]:
    """Probability of each pre-registered outcome (normal approx., Wald SE).

    Outcomes follow the decision table: extend if estimate >= threshold and
    the 95 % CI excludes zero; below threshold if CI excludes zero but the
    estimate is lower; inconclusive if CI covers both 0 and threshold; stop
    if CI covers 0 but not the threshold (audit item 7).

    Args:
        n_arm: groups per arm.
        p_control: restriction share without the signal.
        effect_pp: true reduction, percentage points.
        threshold_pp: extension threshold, percentage points.

    Returns:
        Outcome -> probability.
    """
    p_treat = p_control - effect_pp / 100
    se = sqrt(p_control * (1 - p_control) / n_arm + p_treat * (1 - p_treat) / n_arm) * 100
    half = Z_ALPHA * se
    z = lambda x: norm_cdf((x - effect_pp) / se)  # P(estimate < x)
    extend = 1 - z(max(threshold_pp, half))
    ci_pos = 1 - z(half)
    # CI covers 0 and threshold: threshold - half <= estimate <= half
    covers_both = max(0.0, z(half) - z(threshold_pp - half))
    harm = z(-half)  # whole CI below zero: signal increases restrictions
    return {"extend": extend, "positive_below_threshold": ci_pos - extend,
            "inconclusive": covers_both, "stop": 1 - ci_pos - covers_both - harm,
            "harm": harm, "se_pp": se}


def o5_ceiling(linked_owners: float, device_share: float, stops: float,
               prevented: float, months_per_stop: float) -> float:
    """Paid months O5 could add in a full year.

    Args:
        linked_owners: owners with device number linked to phone.
        device_share: share with a device SIM (E35).
        stops: stops for non-payment per device SIM per year (E35).
        prevented: share of stops prevented by the signal.
        months_per_stop: paid months saved per prevented stop.

    Returns:
        Extra paid months.
    """
    return linked_owners * device_share * stops * prevented * months_per_stop


def o3_net_per_event(months_saved: float, numbers: float, cannibal_share: float,
                     addon_margin_rub: float) -> float:
    """Gross profit change per prevented restriction, RUB.

    Formula: months_saved * numbers * 500 - cannibal_share * addon_margin.

    Args:
        months_saved: paid months saved per affected number.
        numbers: numbers whose payment is affected.
        cannibal_share: share of prevented restrictions where the family would
            have bought an add-on pack instead.
        addon_margin_rub: gross profit of one add-on pack (unknown, Q7).

    Returns:
        RUB per prevented restriction.
    """
    return months_saved * numbers * GP_PER_PAID_MONTH_RUB - cannibal_share * addon_margin_rub


def main() -> None:
    """Print sample sizes, recruitment time, O5 ceilings and per-event values."""
    print("== Groups per arm (alpha 5 %, power 80 %) ==")
    for pc, pt in ((0.12, 0.09), (0.12, 0.08), (0.12, 0.07), (0.15, 0.10)):
        n = n_per_arm(pc, pt)
        print(f"  {pc:.0%} -> {pt:.0%}: {n} per arm, {2 * n} total")
    print("== Eligible group-months per week vs distinct first-time groups ==")
    n7, n9 = 2 * n_per_arm(0.12, 0.07), 2 * n_per_arm(0.12, 0.09)
    for low in (0.15, 0.25, 0.35):
        for elig in (0.3, 0.5, 0.7):
            flow = eligible_weekly_flow(GROUPS_BASE, low, elig)
            u13 = unique_first_groups(GROUPS_BASE, low, elig, 13)
            w7 = weeks_to_recruit(GROUPS_BASE, low, elig, n7)
            w9 = weeks_to_recruit(GROUPS_BASE, low, elig, n9)
            fmt = lambda w: "pool too small" if w is None else f"{w:5.1f}"
            print(f"  low {low:.0%} elig {elig:.0%}: {flow:5.0f} group-months/wk; "
                  f"13 wk: {flow * 13:5.0f} group-months vs {u13:5.0f} distinct; "
                  f"first-week distinct {unique_first_groups(GROUPS_BASE, low, elig, 1):4.0f}; "
                  f"weeks to {n7}: {fmt(w7)}; to {n9}: {fmt(w9)}")
    print("== First-event model: result date for 1 078 distinct groups, start 1 June 2027 ==")
    for groups in (6_500, 8_000):
        dates = []
        for low in (0.15, 0.25, 0.35):
            for elig in (0.3, 0.5, 0.7):
                d = result_date_first_events(groups, low, elig, n7)
                w9 = weeks_to_recruit(groups, low, elig, n9)
                dates.append(d)
                print(f"  {groups} groups, low {low:.0%} elig {elig:.0%}: result "
                      f"{d.isoformat() if d else 'pool too small'}; 3 276 groups: "
                      f"{'pool too small' if w9 is None else f'{w9:.1f} weeks'}")
        ok = [d for d in dates if d]
        print(f"  {groups} groups: earliest {min(ok).isoformat()}, latest {max(ok).isoformat()}")
    print("== Whole-plan error under zero effect (two looks, extension +320 per arm) ==")
    for z1, z2, label in ((1.96, 2.576, "95 % then 99 %"), (1.96, 1.96, "95 % then 95 %")):
        r = overall_false_positive(539, 320, 0.12, z1, z2)
        print(f"  {label}: look 1 {r['look1']:.2%}, after extension {r['after_extension']:.2%}, "
              f"total one-sided {r['total']:.2%} (two-sided equivalent {2 * r['total']:.2%}); "
              f"extended {r['extended']:.1%}")
    for z in (2.10, 2.15, 2.18, 2.20, 2.24):
        r = overall_false_positive(539, 320, 0.12, z, z)
        print(f"  same critical value {z:.2f} at both looks: total one-sided {r['total']:.2%}")
    print("== Probability of each decision outcome, 539 per arm, control 12 % ==")
    for eff in (0.0, 3.0, 5.0, 7.0):
        pr = decision_probabilities(539, 0.12, eff)
        print(f"  true effect {eff:.0f} p.p. (SE {pr['se_pp']:.2f}): extend {pr['extend']:.1%}; "
              f"positive below 5 {pr['positive_below_threshold']:.1%}; inconclusive "
              f"{pr['inconclusive']:.1%}; stop {pr['stop']:.1%}; harm {pr['harm']:.1%}")
    print("== O5 paid-month ceiling, full year ==")
    for owners in (1_000, 2_000, 4_000, ACCESSIBLE_OWNERS):
        lo = o5_ceiling(owners, 0.4, 0.3, 0.3, 0.3)
        hi = o5_ceiling(owners, 0.7, 1.0, 0.5, 1.0)
        print(f"  linked {owners:>6}: {lo:,.0f}-{hi:,.0f} months, "
              f"{lo * 500 / 1e6:.2f}-{hi * 500 / 1e6:.2f} mln RUB")
    print("== Value per prevented event, RUB ==")
    print(f"  O5 stop: {0.3 * 500:.0f}-{1.0 * 500:.0f} (0.3-1 paid month of one number)")
    for margin in (100, 200, 300):
        lo = o3_net_per_event(0.0, 1.0, 0.5, margin)
        hi = o3_net_per_event(0.3, 1.0, 0.1, margin)
        print(f"  O3 restriction, add-on margin {margin}: {lo:.0f} to {hi:.0f}")


if __name__ == "__main__":
    main()
