"""Baseline arithmetic for task 01-family-devices.

Inputs are training numbers from the brief (S1, E-numbers in comments)
and explicitly labelled assumptions (low/high). Run:
    python projects/operator-n-family/tasks/01-family-devices/work/calc_baseline.py
"""

from dataclasses import dataclass

# Brief facts (S1)
ACCESSIBLE_HOUSEHOLDS = 100_000  # E1
ACCESSIBLE_OWNERS = 40_000  # E1
GP = {"plan_base": 282.0, "est_base": 275.0, "nochange": 279.0, "target": 285.0}  # E4, mln RUB
ACTIVE = {"plan_base": 5_000, "est_base": 4_000, "nochange": 5_000, "target": 8_000}  # E5
CONNECTED = {"plan_base": 7_500, "est_base": 6_500, "nochange": 8_000, "target": 12_000}  # E6
OWNERS = {"plan_base": 1_000, "est_base": 800, "nochange": 1_000, "target": 2_000}  # E7
ACTIVATION = {"plan_base": 0.50, "est_base": 0.42, "nochange": 0.45, "target": 0.60}  # E8
GP_PER_PAID_MONTH_RUB = 500  # E9


@dataclass(frozen=True)
class Range:
    """Low/high assumption pair."""

    low: float
    high: float


def decompose_active_gap() -> dict[str, float]:
    """Split the base-year active-groups gap into volume and rate parts.

    Returns:
        Dict with rates and the two components (groups).
    """
    rate_plan = ACTIVE["plan_base"] / CONNECTED["plan_base"]
    rate_est = ACTIVE["est_base"] / CONNECTED["est_base"]
    volume_part = (CONNECTED["est_base"] - CONNECTED["plan_base"]) * rate_plan
    rate_part = CONNECTED["est_base"] * (rate_est - rate_plan)
    return {"rate_plan": rate_plan, "rate_est": rate_est,
            "volume_part": volume_part, "rate_part": rate_part,
            "total": volume_part + rate_part}


def coverage() -> dict[str, float]:
    """Coverage shares of accessible bases.

    Returns:
        Shares for families and owners: base estimate, no-change, target.
    """
    out: dict[str, float] = {}
    for key in ("est_base", "nochange", "target"):
        out[f"fam_{key}"] = CONNECTED[key] / ACCESSIBLE_HOUSEHOLDS
        out[f"own_{key}"] = OWNERS[key] / ACCESSIBLE_OWNERS
    return out


def targets_bridge() -> dict[str, float]:
    """Arithmetic the brief asks to make explicit.

    Returns:
        Net growth, gap to no-change, needed active rate, profit gap.
    """
    return {
        "fam_net_growth_to_target": CONNECTED["target"] - CONNECTED["est_base"],
        "fam_gap_target_vs_nochange": CONNECTED["target"] - CONNECTED["nochange"],
        "active_rate_needed": ACTIVE["target"] / CONNECTED["target"],
        "active_rate_nochange": ACTIVE["nochange"] / CONNECTED["nochange"],
        "active_rate_base": ACTIVE["est_base"] / CONNECTED["est_base"],
        "active_if_target_conn_at_nochange_rate":
            CONNECTED["target"] * ACTIVE["nochange"] / CONNECTED["nochange"],
        "gp_gap_mln": GP["target"] - GP["nochange"],
        "paid_months_needed": (GP["target"] - GP["nochange"]) * 1e6 / GP_PER_PAID_MONTH_RUB,
        "gp_base_gap_mln": GP["plan_base"] - GP["est_base"],
        "owners_gap_target_vs_nochange": OWNERS["target"] - OWNERS["nochange"],
    }


# Assumptions for problem sizing (labelled H in evidence; not brief facts)
NUMBERS_PER_GROUP = Range(2.5, 3.5)  # organizer + participants
SHARE_GROUPS_LOW_BALANCE_MONTH = Range(0.15, 0.35)  # a participant hits low share
RESTRICT_7D_NO_HELP = Range(0.09, 0.15)  # brief example uses 12 %
SHARE_GROUPS_CHARGE_QUESTION_YEAR = Range(0.20, 0.35)  # unclear charge at least once/yr (E65; was 0.40 in code vs 0.35 in E34, audit item 1)
SHARE_GROUPS_MISSED_PAYMENT_YEAR = Range(0.05, 0.15)  # participant blocked for non-payment
SHARE_OWNERS_WITH_DEVICE_SIM = Range(0.40, 0.70)  # router/tablet SIM among owners
DEVICE_STOPS_PER_YEAR = Range(0.3, 1.0)  # stops for non-payment per device SIM


def size_problems(groups: float, owners: float) -> dict[str, tuple[float, float]]:
    """Distinct units affected per year for four candidate problems.

    Args:
        groups: connected family groups in scope.
        owners: connected multi-number owners in scope.

    Returns:
        Problem name -> (low, high) affected units per year or events.
    """
    lb = SHARE_GROUPS_LOW_BALANCE_MONTH
    restr = RESTRICT_7D_NO_HELP
    return {
        "P1 low-balance events per year (group-months)": (groups * lb.low * 12, groups * lb.high * 12),
        "P1 restrictions per year (no help)": (groups * lb.low * 12 * restr.low,
                                               groups * lb.high * 12 * restr.high),
        "P2 groups with unclear charge per year": (groups * SHARE_GROUPS_CHARGE_QUESTION_YEAR.low,
                                                   groups * SHARE_GROUPS_CHARGE_QUESTION_YEAR.high),
        "P3 groups with participant blocked for non-payment": (
            groups * SHARE_GROUPS_MISSED_PAYMENT_YEAR.low, groups * SHARE_GROUPS_MISSED_PAYMENT_YEAR.high),
        "P4 device stops for non-payment per year": (
            owners * SHARE_OWNERS_WITH_DEVICE_SIM.low * DEVICE_STOPS_PER_YEAR.low,
            owners * SHARE_OWNERS_WITH_DEVICE_SIM.high * DEVICE_STOPS_PER_YEAR.high),
        "P4 if offered to all accessible owners": (
            ACCESSIBLE_OWNERS * SHARE_OWNERS_WITH_DEVICE_SIM.low * DEVICE_STOPS_PER_YEAR.low,
            ACCESSIBLE_OWNERS * SHARE_OWNERS_WITH_DEVICE_SIM.high * DEVICE_STOPS_PER_YEAR.high),
    }


def p1_profit_upper_bound(groups: float) -> dict[str, float]:
    """Generous ceiling of paid months P1 could add in a full year.

    Every prevented restriction is assumed to save one paid month for every
    number in the group (deliberately too generous) and half of restrictions
    are prevented.

    Args:
        groups: connected family groups in scope.

    Returns:
        Ceiling of extra paid months and gross profit, mln RUB.
    """
    restrictions = groups * SHARE_GROUPS_LOW_BALANCE_MONTH.high * 12 * RESTRICT_7D_NO_HELP.high
    months = restrictions * 0.5 * NUMBERS_PER_GROUP.high
    return {"restrictions_high": restrictions, "months_ceiling": months,
            "gp_ceiling_mln": months * GP_PER_PAID_MONTH_RUB / 1e6}


def main() -> None:
    """Print all baseline numbers with inputs."""
    print("== Active gap decomposition (base year, plan vs estimate) ==")
    for k, v in decompose_active_gap().items():
        print(f"  {k}: {v:.3f}")
    print("== Coverage shares ==")
    for k, v in coverage().items():
        print(f"  {k}: {v:.1%}")
    print("== Targets bridge ==")
    for k, v in targets_bridge().items():
        print(f"  {k}: {v:,.3f}")
    print("== Numbers in groups (assumption 2.5-3.5 per group) ==")
    for key in ("est_base", "nochange", "target"):
        g = CONNECTED[key]
        print(f"  {key}: {g * NUMBERS_PER_GROUP.low:,.0f}-{g * NUMBERS_PER_GROUP.high:,.0f}")
    print("== Problem sizing, base-year connected (6 500 groups, 800 owners) ==")
    for k, (lo, hi) in size_problems(CONNECTED["est_base"], OWNERS["est_base"]).items():
        print(f"  {k}: {lo:,.0f}-{hi:,.0f}")
    print("== P1 generous profit ceiling, full year, groups at no-change level 8 000 ==")
    for k, v in p1_profit_upper_bound(CONNECTED["nochange"]).items():
        print(f"  {k}: {v:,.2f}")


if __name__ == "__main__":
    main()
