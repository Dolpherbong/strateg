"""Gap pricing for task 01-family-devices (stage 6 fix, three open gaps).

1. Cost per additional (incremental) connection by channel.
2. Direct costs of the low-balance signal.
3. Price of closing the gaps: connected groups, active groups, activation, owners.

All unit costs and effects are labelled assumptions (E55, E57, E59). Run:
    python projects/operator-n-family/tasks/01-family-devices/work/calc_gaps.py
"""

GP_PER_PAID_MONTH_RUB = 500  # E9
GROUPS_NO_CHANGE = 8_000  # E6
GROUPS_TARGET = 12_000  # E6
ACTIVE_SHARE_NO_CHANGE = 5_000 / 8_000  # E5, E6
ACTIVE_TARGET = 8_000  # E5
OWNERS_NO_CHANGE = 1_000  # E7
OWNERS_TARGET = 2_000  # E7
OWNERS_ACCESSIBLE = 40_000  # E1

# E55: cost per shown offer, RUB, and incremental conversion vs usual service
CHANNELS = {
    "app": {"reach": (37_000, 56_000), "cost": (0.5, 2.0), "incr": (0.005, 0.02)},
    "sales": {"reach": (10_000, 20_000), "cost": (30.0, 80.0), "incr": (0.02, 0.06)},
    "support": {"reach": (5_000, 10_000), "cost": (20.0, 60.0), "incr": (0.02, 0.06)},
}


def cac(cost_per_offer: float, incremental_conversion: float) -> float:
    """Cost per additional connection: spend / connections above usual service.

    Args:
        cost_per_offer: RUB per distinct client who sees the offer.
        incremental_conversion: extra share connecting vs usual service.

    Returns:
        RUB per additional connection.
    """
    return cost_per_offer / incremental_conversion


def channel_block() -> tuple[float, float, float, float]:
    """Print CAC and reachable extra connections per channel.

    Returns:
        (extra_low, extra_high, spend_low, spend_high) summed over channels.
    """
    print("== 1. Cost per additional connection (E55) ==")
    print("  spend = reach x cost per shown offer; extra = reach x incremental conversion "
          "(audit item 12: spend no longer mixes low and high conversion)")
    tot = [0.0, 0.0, 0.0, 0.0]
    for ch, p in CHANNELS.items():
        c_best = cac(p["cost"][0], p["incr"][1])
        c_worst = cac(p["cost"][1], p["incr"][0])
        x_lo = p["reach"][0] * p["incr"][0]
        x_hi = p["reach"][1] * p["incr"][1]
        s_lo, s_hi = p["reach"][0] * p["cost"][0], p["reach"][1] * p["cost"][1]
        tot = [tot[0] + x_lo, tot[1] + x_hi, tot[2] + s_lo, tot[3] + s_hi]
        print(f"  {ch:<8} CAC {c_best:,.0f}-{c_worst:,.0f} RUB; extra groups/yr "
              f"{x_lo:,.0f}-{x_hi:,.0f}; spend {s_lo / 1e3:,.1f}-{s_hi / 1e3:,.1f} thousand RUB")
        for r_i, r_name in ((0, "low reach"), (1, "high reach")):
            for c_i in (0, 1):
                for i_i in (0, 1):
                    s = p["reach"][r_i] * p["cost"][c_i]
                    x = p["reach"][r_i] * p["incr"][i_i]
                    if (c_i, i_i) in ((0, 1), (1, 0)):
                        print(f"    {r_name}, cost {p['cost'][c_i]}, incr {p['incr'][i_i]:.1%}: "
                              f"spend {s / 1e3:,.1f} thousand, extra {x:,.0f}, per group {s / x:,.0f}")
    print(f"  all channels: extra {tot[0]:,.0f}-{tot[1]:,.0f} groups/yr, "
          f"spend {tot[2] / 1e3:,.1f}-{tot[3] / 1e3:,.1f} thousand RUB")
    for months, numbers in ((0.5, 2.5), (1.0, 3.0), (2.0, 3.5)):
        print(f"  break-even CAC if a new group keeps {months} extra paid month on "
              f"{numbers} numbers: {months * numbers * GP_PER_PAID_MONTH_RUB:,.0f} RUB")
    return tot[0], tot[1], tot[2], tot[3]


def signal_costs(low: float, elig: float, sms_share: float, sms_rub: float,
                 contacts_per_100: float, contact_rub: float) -> float:
    """Direct yearly cost of signals at 8 000 groups, RUB (E57).

    Messages: 2 per eligible low-balance case (organizer and participant);
    only the SMS share costs money, push is treated as free.

    Args:
        low: monthly low-balance share (E33).
        elig: eligible share (E39).
        sms_share: share of messages that go by SMS (no app).
        sms_rub: RUB per SMS.
        contacts_per_100: extra support contacts per 100 signalled cases.
        contact_rub: RUB per support contact.

    Returns:
        RUB per year.
    """
    cases = GROUPS_NO_CHANGE * low * 12 * elig
    sms = cases * 2 * sms_share * sms_rub
    support = cases / 100 * contacts_per_100 * contact_rub
    return sms + support


def cost_per_case(sms_share: float, sms_rub: float, contacts_per_100: float,
                  contact_rub: float) -> float:
    """Direct cost of one signalled case, RUB (2 messages + extra support)."""
    return 2 * sms_share * sms_rub + contacts_per_100 / 100 * contact_rub


def costs_block() -> None:
    """Print direct signal costs. Profit after costs lives in calc_strategy.py."""
    print("== 2. Direct costs of signals, full year, 8 000 groups (E57) ==")
    vol = {"cautious": (0.15, 0.3), "base": (0.25, 0.5), "bold": (0.35, 0.7)}
    for name, (low, elig) in vol.items():
        lo = signal_costs(low, elig, 0.2, 1.0, 0.0, 50.0)
        hi = signal_costs(low, elig, 0.5, 3.0, 2.0, 150.0)
        print(f"  {name:<8}: costs {lo / 1e6:.4f}-{hi / 1e6:.4f} mln/yr at full coverage")
    c_lo, c_hi = cost_per_case(0.2, 1.0, 0.0, 50.0), cost_per_case(0.5, 3.0, 2.0, 150.0)
    # Every signal-arm group has had its eligible first event (audit item 14).
    print(f"  per case {c_lo:.1f}-{c_hi:.1f} RUB; pilot signal arm, 539 first events: "
          f"{539 * c_lo:,.0f}-{539 * c_hi:,.0f} RUB; repeat and unsent signals counted separately")


ROLLOUT_COVERAGE = 0.9  # same holdout as calc_strategy.py


def signal_active(groups: float, low: float, elig: float, act: float) -> float:
    """Extra active groups from the signal in the last month (formula of E49).

    Assumes the inactive share among eligible groups equals the overall
    37.5 % (an assumption, audit item 19).
    """
    return groups * low * elig * (1 - ACTIVE_SHARE_NO_CHANGE) * act * ROLLOUT_COVERAGE


def gaps_block(extra_lo: float, extra_hi: float) -> None:
    """Print the price of closing each gap."""
    print("== 3. Price of closing gaps ==")
    gap_groups = GROUPS_TARGET - GROUPS_NO_CHANGE
    print(f"  connected groups: gap {gap_groups:,}; existing channels give "
          f"{extra_lo:,.0f}-{extra_hi:,.0f}; uncovered {gap_groups - extra_hi:,.0f}-"
          f"{gap_groups - extra_lo:,.0f}")
    for c in (500, 1_000, 2_000):
        print(f"    if all 4 000 at CAC {c} RUB: {gap_groups * c / 1e6:.1f} mln RUB")
    print(f"    with retention: up to {extra_hi:,.0f} new + 650-1 300 avoided exits (E45) = "
          f"{extra_hi + 650:,.0f}-{extra_hi + 1_300:,.0f} before overlap corrections; "
          f"price = channel spend + retention cost + remainder x new-channel CAC (last two unknown)")
    from_groups = gap_groups * ACTIVE_SHARE_NO_CHANGE
    # One bridge from the main forecast (audit item 20); signal recomputed,
    # not scaled from the rounded 169, with the same 10 % holdout (item 19).
    sig_8k = signal_active(GROUPS_NO_CHANGE, 0.25, 0.5, 0.45)
    sig_12k_lo = signal_active(GROUPS_TARGET, 0.25, 0.5, 0.45)
    sig_12k_hi = signal_active(GROUPS_TARGET, 0.35, 0.7, 0.60)
    main = 5_000 + sig_8k
    reached = main + from_groups + (sig_12k_lo - sig_8k)
    print(f"  active groups: main forecast {main:,.3f} (signal {sig_8k:,.3f}); "
          f"+{from_groups:,.0f} with new groups at 62.5 %; +{sig_12k_lo - sig_8k:,.3f} "
          f"extra signal on new groups = {reached:,.3f}; remainder {ACTIVE_TARGET - reached:,.3f}")
    hi_total = GROUPS_TARGET * ACTIVE_SHARE_NO_CHANGE + sig_12k_hi
    print(f"    upper scenario: 7 500 + signal {sig_12k_hi:,.3f} = {hi_total:,.1f}; "
          f"remainder {max(ACTIVE_TARGET - hi_total, 0):,.1f}")
    print("    price of the remainder: remainder x cost per extra active group; cost per "
          "extra active group unknown (needs the pilot difference in monthly activity)")
    for acc in (0.55, 0.60, 0.62, 0.70):  # E43
        need = 0.60 / acc
        print(f"  activation 60 % = accepted-in-time x acting-in-time: acceptance {acc:.0%} -> "
              f"{need:.1%} of accepted must act" + (" (impossible)" if need > 1 else ""))
    print("    minimum acceptance is 60 % at 100 % acting; 62 % corresponds to ~97 % acting")
    for created in (3_070, 5_090):  # E45
        q4 = created / 4
        print(f"    Q4 cohort {q4:,.0f} groups: +15 p.p. = {q4 * 0.15:,.0f} groups; "
              f"reminder SMS {q4 * 2 * 1:,.0f}-{q4 * 2 * 3:,.0f} RUB per quarter")
    need = OWNERS_TARGET - OWNERS_NO_CHANGE
    pool = OWNERS_ACCESSIBLE - OWNERS_NO_CHANGE
    for reach in (0.4, 0.7):
        print(f"  owners: gap {need:,}; reach {reach:.0%} of {pool:,} -> incremental "
              f"linking {need / (pool * reach):.1%}; offer cost at 0.5-2 RUB "
              f"{pool * reach * 0.5 / 1e3:.0f}-{pool * reach * 2 / 1e3:.0f} thousand RUB")


def family_scenarios() -> None:
    """Consistent channel scenarios: spend and extra groups from the same inputs.

    A: low reach, cheap offer, strong increment; B: high reach, dear offer,
    weak increment (audit-2 item 5 of the jury list). Totals are never
    glued from extremes of different scenarios.
    """
    for label, r_i, c_i, i_i in (("A low reach, cheap, strong", 0, 0, 1),
                                 ("B high reach, dear, weak", 1, 1, 0)):
        spend = sum(p["reach"][r_i] * p["cost"][c_i] for p in CHANNELS.values())
        extra = sum(p["reach"][r_i] * p["incr"][i_i] for p in CHANNELS.values())
        rem = GROUPS_TARGET - GROUPS_NO_CHANGE - extra
        print(f"  families {label}: spend {spend / 1e3:,.1f} thousand RUB for {extra:,.0f} groups "
              f"({spend / extra:,.0f} RUB/group); remainder {rem:,.0f}; with 650-1 300 avoided "
              f"exits {rem - 1_300:,.0f}-{rem - 650:,.0f} x new-channel price (unknown)")


def goal_prices() -> None:
    """Price of reaching each goal in its own units; unknown inputs named."""
    print("== 4. Price of reaching the five goals (units: RUB or person-months per unit of the goal) ==")
    print("  profit: required 12 018-12 049 paid months (E77); price per month = measure cost / "
          "extra months; signal even at strong link (3.5 numbers keep 1 month) gives per year:")
    for name, prevented in (("cautious", 194.4), ("base", 540.0), ("bold", 1_058.4)):
        months = prevented * 3.5
        print(f"    {name}: {months:,.0f} months/yr = {months / 12_018:.1%} of required")
    family_scenarios()
    dev_pm, active = (2.0, 3.0), (151.875, 396.9)
    q4_costs = (1_080, 16_200)
    print(f"  active groups: signal {active[0]:.0f}-{active[1]:.0f} extra in December for "
          f"{dev_pm[0]}-{dev_pm[1]} person-months + {q4_costs[0]:,}-{q4_costs[1]:,} RUB: "
          f"{dev_pm[0] / active[1]:.3f}-{dev_pm[1] / active[0]:.3f} person-months and "
          f"{q4_costs[0] / active[1]:.0f}-{q4_costs[1] / active[0]:.0f} RUB per extra active group; "
          f"remainder 272 x price of a further measure (unknown)")
    print("  activation: price per extra activated group = (0.5-1 person-month + 1 535-7 635 RUB SMS "
          "per quarter) / extra activated groups vs random control (unknown); +15 p.p. = 115-191 groups")
    print("  owners: price per extra stable link = (8-55 thousand RUB offers + 2-3 person-months O5 + "
          "execution costs) / (stable links after 3 months minus control); 1 000 links needed")


def main() -> None:
    """Run all blocks."""
    x_lo, x_hi, _, _ = channel_block()
    costs_block()
    gaps_block(x_lo, x_hi)
    goal_prices()


if __name__ == "__main__":
    main()
