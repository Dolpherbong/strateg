"""Strategy-stage arithmetic for task 01-family-devices (chosen option O3).

Covers the funnel reconciliation, own forecast for the five brief rows,
profit scenarios and the maximum investment that can pay back.
Inputs are brief facts (E-numbers) and labelled assumptions. Run:
    python projects/operator-n-family/tasks/01-family-devices/work/calc_strategy.py
"""

from datetime import date, timedelta
from math import ceil

GP_PER_PAID_MONTH_RUB = 500  # E9
GROUPS_START = 6_500  # E6, base-year estimate
GROUPS_NO_CHANGE = 8_000  # E6
ACTIVE_NO_CHANGE = 5_000  # E5
ACCESSIBLE_HOUSEHOLDS = 100_000  # E1
GP_NO_CHANGE_MLN = 279.0  # E4
BASE_MISS_GROUPS = 6_500 / 7_500  # E6: base-year estimate vs plan
BASE_MISS_GP = 275 / 282  # E4
BASE_ACTIVE_SHARE = 4_000 / 6_500  # E5, E6
THRESHOLD_PP = 0.05  # absolute 5 p.p. reduction per eligible case, E38 (audit item 15)
ROLLOUT_COVERAGE = 0.9  # 10 % of first-time eligible groups stay without signal after rollout
COST_PER_CASE_RUB = (0.4, 6.0)  # E57: 2 msgs x 20-50 % SMS x 1-3 RUB + 0-2/100 contacts x 50-150
PILOT_START = date(2027, 6, 1)
OBSERVATION_DAYS = 7
CHANNEL_SPLIT = {"app": 0.60, "sales": 0.25, "support": 0.15}  # hypothesis E44
CHANNEL_REACH = {"app": (37_000, 56_000), "sales": (10_000, 20_000),
                 "support": (5_000, 10_000)}  # hypothesis E44, distinct households/year


def funnel_no_change(churn: float, acceptance: float) -> dict[str, float]:
    """Reconcile start + new - exits = end for the no-change forecast.

    Args:
        churn: share of start-of-year groups that disconnect during the year.
        acceptance: share of created groups where an invitation is accepted.

    Returns:
        Exits, new connected groups and created groups needed.
    """
    exits = GROUPS_START * churn
    new_connected = GROUPS_NO_CHANGE - GROUPS_START + exits
    created = new_connected / acceptance
    return {"exits": exits, "new_connected": new_connected, "created": created}


def implied_channel_conversion(created: float) -> dict[str, tuple[float, float]]:
    """Share of reached households that create a group, per channel.

    Each group is attributed to the last channel before creation, so the
    channel totals add up to the created total without double counting.

    Args:
        created: groups created in the year.

    Returns:
        Channel -> (conversion at high reach, conversion at low reach).
    """
    out = {}
    for ch, share in CHANNEL_SPLIT.items():
        lo_reach, hi_reach = CHANNEL_REACH[ch]
        out[ch] = (created * share / hi_reach, created * share / lo_reach)
    return out


def active_uplift(groups: float, low: float, elig: float, act: float,
                  base_share: float = ACTIVE_NO_CHANGE / GROUPS_NO_CHANGE) -> float:
    """Extra active groups in the last month from the signal.

    Only groups not already active can add to the count, and only if someone
    opens the balance or transfers from the signal.

    Args:
        groups: connected groups at year end.
        low: share of groups with a low-balance event per month (E33).
        elig: share eligible for the signal (E39).
        act: share of signalled, otherwise inactive groups that act (E46).
        base_share: active share without changes (E5, E6).

    Returns:
        Extra active groups.
    """
    return groups * low * elig * (1 - base_share) * act


def signalled_cases(groups: float, low: float, elig: float, months: float,
                    coverage: float = ROLLOUT_COVERAGE) -> float:
    """Eligible low-balance cases that receive a signal (events, repeats included).

    Args:
        groups: connected groups.
        low: monthly low-balance share (E33).
        elig: eligible share (E39).
        months: months the signal works.
        coverage: share of eligible groups outside the holdout.

    Returns:
        Signalled cases.
    """
    return groups * low * elig * months * coverage


def prevented_events(cases: float) -> float:
    """Restrictions prevented at exactly the 5 p.p. threshold (absolute).

    Applies the pilot effect (measured on first events) to every case,
    which is an assumption (audit items 8 and 15).

    Args:
        cases: signalled eligible cases.

    Returns:
        Prevented restrictions.
    """
    return cases * THRESHOLD_PP


def contribution_after_costs(cases: float, net_rub: float) -> tuple[float, float]:
    """Gross profit change after direct signal costs, RUB (low, high).

    Args:
        cases: signalled eligible cases.
        net_rub: gross profit change per prevented restriction (E41).

    Returns:
        (after high unit costs, after low unit costs).
    """
    gross = prevented_events(cases) * net_rub
    return gross - cases * COST_PER_CASE_RUB[1], gross - cases * COST_PER_CASE_RUB[0]


def months_needed_for_target(gap_mln: float, new_costs_rub: float,
                             lost_margin_rub: float, other_rub: float = 0.0) -> float:
    """Paid months needed to close the profit gap with costs (audit item 17).

    M >= (gap + new direct costs + lost add-on margin - other contributions) / 500.

    Args:
        gap_mln: profit gap, mln RUB (E30).
        new_costs_rub: new direct costs, RUB.
        lost_margin_rub: lost add-on margin, RUB.
        other_rub: other contributions, RUB.

    Returns:
        Extra paid months.
    """
    return (gap_mln * 1e6 + new_costs_rub + lost_margin_rub - other_rub) / GP_PER_PAID_MONTH_RUB


def net_per_event(months_saved: float, cannibal: float, addon_margin: float) -> float:
    """Gross profit per prevented restriction, RUB (formula of E41)."""
    return months_saved * GP_PER_PAID_MONTH_RUB - cannibal * addon_margin


def print_funnel() -> None:
    """Print the no-change funnel and implied channel conversions."""
    print("== Funnel without changes: 6 500 + new - exits = 8 000 ==")
    for churn, acc in ((0.10, 0.70), (0.15, 0.62), (0.20, 0.55)):
        f = funnel_no_change(churn, acc)
        act = f["created"] * 0.45  # E8, activated within 14 days
        print(f"  churn {churn:.0%} accept {acc:.0%}: exits {f['exits']:,.0f}, "
              f"new {f['new_connected']:,.0f}, created {f['created']:,.0f}, "
              f"activated {act:,.0f}")
        for ch, (c_lo, c_hi) in implied_channel_conversion(f["created"]).items():
            print(f"    {ch:<8} created {f['created'] * CHANNEL_SPLIT[ch]:>6,.0f}, "
                  f"conversion {c_lo:.1%}-{c_hi:.1%}")


def print_forecast() -> None:
    """Print own forecast for the five brief rows (rollout with 10 % holdout)."""
    print("== Own forecast, plan year (Q4 rollout, 90 % of eligible groups get the signal) ==")
    main_up = active_uplift(GROUPS_NO_CHANGE, 0.25, 0.5, 0.45) * ROLLOUT_COVERAGE
    print(f"  main: connected {GROUPS_NO_CHANGE}, active {ACTIVE_NO_CHANGE + main_up:,.2f} "
          f"(+{main_up:,.2f} from Q4 rollout), activation 45 %, owners 1 000")
    lf_groups = GROUPS_NO_CHANGE * BASE_MISS_GROUPS
    lf_active = lf_groups * BASE_ACTIVE_SHARE
    print(f"  less favourable: connected {lf_groups:,.2f}, active {lf_active:,.2f} "
          f"(no rollout), activation 42 %, owners 800, "
          f"GP {GP_NO_CHANGE_MLN * BASE_MISS_GP:.3f} mln")
    hi_up = active_uplift(GROUPS_NO_CHANGE, 0.35, 0.7, 0.6) * ROLLOUT_COVERAGE
    print(f"  upper bound of active uplift: +{hi_up:,.2f}")
    q4_cases = signalled_cases(GROUPS_NO_CHANGE, 0.25, 0.5, 3)
    q4 = prevented_events(q4_cases)
    lo_gp = contribution_after_costs(q4_cases, -150)[0]
    hi_gp = contribution_after_costs(q4_cases, 140)[1]
    print(f"  Q4 signalled cases {q4_cases:,.0f}, prevented {q4:,.0f}; GP before costs "
          f"{q4 * -150:+,.0f} to {q4 * 140:+,.0f} RUB; after direct costs {lo_gp:+,.0f} to "
          f"{hi_gp:+,.0f} RUB")
    pilot_cases = 539  # one first event per signal-arm group
    pilot_gp = (pilot_cases * THRESHOLD_PP * -150 - pilot_cases * COST_PER_CASE_RUB[1],
                pilot_cases * THRESHOLD_PP * 140 - pilot_cases * COST_PER_CASE_RUB[0])
    print(f"  pilot signal arm (first events only): {pilot_gp[0]:+,.0f} to {pilot_gp[1]:+,.0f} RUB; "
          f"plan-year bridge {GP_NO_CHANGE_MLN + (lo_gp + pilot_gp[0]) / 1e6:.4f}-"
          f"{GP_NO_CHANGE_MLN + (hi_gp + pilot_gp[1]) / 1e6:.4f} mln before development cost")
    lost = q4 * 0.3 * 200  # base scenario lost add-on margin, 60 RUB per prevention
    for cost_rub in (q4_cases * COST_PER_CASE_RUB[0], q4_cases * COST_PER_CASE_RUB[1]):
        print(f"  months needed for +6 mln with Q4 costs {cost_rub:,.0f} RUB and lost margin "
              f"{lost:,.0f} RUB: {months_needed_for_target(6.0, cost_rub, lost):,.0f}")


QUARTERS_TO_END_2029 = 9  # broad rollout from Q4 2027 to Q4 2029


def print_economics() -> None:
    """Print full-year scenarios after direct costs and cumulative payback by quarter.

    Effect is the absolute 5 p.p. threshold in every scenario (audit item 15);
    rollout keeps a 10 % holdout (item 19); payback is cumulative over the
    9 quarters of broad rollout to end of 2029, not 3 full years (item 18).
    """
    print("== Full year at scale, 8 000 groups, 90 % coverage, 5 p.p. absolute ==")
    scenarios = {
        "cautious": (0.15, 0.3, net_per_event(0.0, 0.5, 300), 0.5 * 300),
        "base": (0.25, 0.5, net_per_event(0.1, 0.3, 200), 0.3 * 200),
        "bold": (0.35, 0.7, net_per_event(0.3, 0.1, 100), 0.1 * 100),
    }
    for name, (low, elig, net, lost) in scenarios.items():
        cases = signalled_cases(GROUPS_NO_CHANGE, low, elig, 12)
        ev = prevented_events(cases)
        after = contribution_after_costs(cases, net)
        q = QUARTERS_TO_END_2029 / 4
        print(f"  {name:<8}: cases {cases:,.0f}, prevented {ev:,.1f}/yr, net {net:+.0f} RUB/event, "
              f"GP before costs {ev * net:+,.0f}; after costs {after[0]:+,.0f} to {after[1]:+,.0f} "
              f"RUB/yr; 9 quarters signed {after[0] * q:+,.0f} to {after[1] * q:+,.0f}")
        strong_net = 3.5 * GP_PER_PAID_MONTH_RUB - lost  # E37 premise minus add-on loss
        s_after = contribution_after_costs(cases, strong_net)
        print(f"    strong retention link (3.5 numbers keep 1 month, minus {lost:.0f} RUB add-on "
              f"loss): {s_after[0]:+,.0f} to {s_after[1]:+,.0f} RUB/yr; cumulative to end 2029 "
              f"{s_after[0] * q:,.0f}-{s_after[1] * q:,.0f}")
    print("== Signed cumulative by quarter after direct costs, incl. pilot (development not included) ==")
    pilot_cases = 539
    for name, (low, elig, net, lost) in scenarios.items():
        cases = signalled_cases(GROUPS_NO_CHANGE, low, elig, 12)
        for eff, label in ((THRESHOLD_PP, "5 p.p."), (0.03, "3 p.p.")):
            gross = cases * eff * net
            ann = (gross - cases * COST_PER_CASE_RUB[1], gross - cases * COST_PER_CASE_RUB[0])
            pg = pilot_cases * eff * net
            pilot = (pg - pilot_cases * COST_PER_CASE_RUB[1], pg - pilot_cases * COST_PER_CASE_RUB[0])
            rows = quarterly_cumulative(ann[0], ann[1], pilot)
            cells = "; ".join(f"{q} {lo:+,.0f}..{hi:+,.0f}" for q, lo, hi in rows
                              if q in ("2027Q3", "2027Q4", "2028Q4", "2029Q4"))
            print(f"  {name:<8} {label}: annual {ann[0]:+,.0f}..{ann[1]:+,.0f}; {cells}")
        strong_net = 3.5 * GP_PER_PAID_MONTH_RUB - lost
        gross = cases * THRESHOLD_PP * strong_net
        ann = (gross - cases * COST_PER_CASE_RUB[1], gross - cases * COST_PER_CASE_RUB[0])
        pg = pilot_cases * THRESHOLD_PP * strong_net
        rows = quarterly_cumulative(ann[0], ann[1], (pg - pilot_cases * 6.0, pg - pilot_cases * 0.4))
        print(f"  {name:<8} strong link 5 p.p.: end 2029 {rows[-1][1]:+,.0f}..{rows[-1][2]:+,.0f}")
    print("  payback quarter = first quarter where cumulative >= (2-3 person-months x rate), rate unknown (Q9)")
    for cannibal, margin in ((0.3, 200), (0.5, 300), (0.1, 100)):
        be = cannibal * margin / GP_PER_PAID_MONTH_RUB
        print(f"  break-even months saved per event: cannibal {cannibal:.0%}, "
              f"margin {margin}: {be:.2f} before costs")
    lo_c, hi_c = (c / THRESHOLD_PP for c in COST_PER_CASE_RUB)
    print(f"  direct costs per prevented restriction {lo_c:.0f}-{hi_c:.0f} RUB = "
          f"{lo_c / GP_PER_PAID_MONTH_RUB:.3f}-{hi_c / GP_PER_PAID_MONTH_RUB:.3f} paid months")


def expected_reduction_pp(baseline: float, act: float) -> float:
    """Upper estimate of the drop in restriction share, percentage points.

    Assumes every timely effective transfer prevents the restriction;
    other groups keep the baseline share.

    Args:
        baseline: restriction share within 7 days without the signal (E33).
        act: share of would-be restrictions where a transfer arrives in time
            (E66). This is a separate assumption from E46, which is about
            opening the balance among otherwise inactive groups (audit item 6).

    Returns:
        Reduction in p.p.
    """
    return baseline * act * 100


def pace_for_deadline(groups_needed: int, weeks_available: float) -> float:
    """First-time eligible groups per week needed to finish recruitment.

    Args:
        groups_needed: total pilot groups (E38).
        weeks_available: weeks from pilot start to decision minus observation.

    Returns:
        Groups per week.
    """
    return groups_needed / weeks_available


def weeks_until(deadline: date) -> float:
    """Recruitment weeks from pilot start to ``deadline`` minus observation.

    No time for analysis is reserved (audit item 9).
    """
    return ((deadline - PILOT_START).days - OBSERVATION_DAYS) / 7


def result_date(groups_needed: int, pace: float) -> date:
    """Earliest date the last recruited group finishes observation.

    Constant distinct-group pace (a conditional rate, not a forecast);
    recruitment days are rounded up to full days (audit-2 item 2).
    """
    return PILOT_START + timedelta(days=ceil(groups_needed / pace * 7) + OBSERVATION_DAYS)


QUARTERS = ["2027Q2", "2027Q3", "2027Q4", "2028Q1", "2028Q2", "2028Q3", "2028Q4",
            "2029Q1", "2029Q2", "2029Q3", "2029Q4"]


def quarterly_cumulative(annual_lo: float, annual_hi: float, pilot: tuple[float, float]
                         ) -> list[tuple[str, float, float]]:
    """Signed cumulative contribution by quarter after direct costs (audit-2 item 3).

    Pilot contribution falls in 2027Q3; broad rollout from 2027Q4 adds a
    quarter of the annual figure each quarter. Development and testing costs
    are not included (rate unknown, Q9) and must be subtracted in 2027Q2.
    No value is clipped at zero.

    Args:
        annual_lo: annual contribution after costs, low.
        annual_hi: annual contribution after costs, high.
        pilot: pilot contribution (low, high).

    Returns:
        (quarter, cumulative low, cumulative high).
    """
    out, lo, hi = [], 0.0, 0.0
    for q in QUARTERS:
        if q == "2027Q3":
            lo, hi = lo + pilot[0], hi + pilot[1]
        elif q >= "2027Q4":
            lo, hi = lo + annual_lo / 4, hi + annual_hi / 4
        out.append((q, lo, hi))
    return out


def print_pilot_checks() -> None:
    """Print expected effect vs threshold and recruitment pace vs deadline."""
    print("== Expected reduction vs 5 p.p. threshold (upper: every timely transfer prevents) ==")
    for base in (0.09, 0.12, 0.15):
        lo, hi = expected_reduction_pp(base, 0.3), expected_reduction_pp(base, 0.6)
        print(f"  baseline {base:.0%}: {lo:.1f}-{hi:.1f} p.p. (timely 30-60 %); "
              f"needed for 5 p.p.: {0.05 / base:.1%}")
    print("== Recruitment pace for 1 078 distinct groups, start 1 June 2027, 7 days observation ==")
    for label, d in (("15 Aug", date(2027, 8, 15)), ("15 Sep", date(2027, 9, 15)),
                     ("30 Sep", date(2027, 9, 30))):
        w = weeks_until(d)
        print(f"  decision {label}: {w:.2f} weeks, {pace_for_deadline(1_078, w):.1f} groups/week")
    for pace in (59, 60, 79, 80):
        print(f"  at constant {pace}/week distinct: recruitment {1_078 / pace:.1f} weeks, result "
              f"{result_date(1_078, pace).isoformat()}")
    print("  forecast dates come from the first-event model in calc_options.py, not from constant paces")
    for pc, pt in ((0.12, 0.12), (0.12, 0.07)):
        se = (pc * (1 - pc) / 539 + pt * (1 - pt) / 539) ** 0.5
        print(f"  95 % CI half-width, 539 per arm, {pc:.0%} vs {pt:.0%}: "
              f"+/-{1.96 * se * 100:.1f} p.p.")


def main() -> None:
    """Run all blocks."""
    print_funnel()
    print_forecast()
    print_economics()
    print_pilot_checks()


if __name__ == "__main__":
    main()
