"""Audit quotes, registry references and conditional arithmetic, not N economics."""
from pathlib import Path
from collections import Counter
from statistics import NormalDist
from datetime import date, timedelta
import hashlib
import json
import math
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT))
from tools.lib.records import load_project

source = ROOT / 'projects/operator-n-travel/inbox/chat-answer.md'
raw = source.read_bytes()
lines = raw.decode('utf-8-sig').splitlines()
rows = json.loads((HERE / 'check-chat-answer.json').read_text(encoding='utf-8'))
index = {r.id: r for r in load_project(ROOT / 'projects/operator-n-travel').records}
for row in rows:
    line = lines[row['line'] - 1].replace('**', '')
    if row['quote'] not in line:
        raise ValueError(f"Quote mismatch: {row['id']} line {row['line']}")
    if len(row['quote'].split()) > 25:
        raise ValueError(f"Quote too long: {row['id']}")
    for ref in row['refs']:
        if ref not in index:
            raise ValueError(f'Missing registry record: {ref}')
    if row['verdict'] != 'нечем подтвердить' and not row['refs']:
        raise ValueError(f"Verdict without support: {row['id']}")

scenarios = []
for m, c in [(80, .5), (180, .2), (300, .1)]:
    u = m - c * 700
    scenarios.append({'m': m, 'c': c, 'u': u,
                      'year_result': 100_000 * u - 4_200_000,
                      'break_even_trips': None if u <= 0 else 4_200_000 / u})
p1, p2 = .03, .04
pooled = (p1 + p2) / 2
normal = NormalDist()
z_alpha = normal.inv_cdf(1 - (.05 / 2) / 2)
z_power = normal.inv_cdf(.8)
n = ((z_alpha * math.sqrt(2 * pooled * (1 - pooled))
      + z_power * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) / (p2 - p1)) ** 2
report = {
    'source_sha256': hashlib.sha256(raw).hexdigest(),
    'claims_total': len(rows),
    'verdict_counts': dict(Counter(r['verdict'] for r in rows)),
    'central_m': 600 - 300 - 70 - 50,
    'scenarios': scenarios,
    'central_cannibalization_boundary': 180 / 700,
    'illustrative_trips': 1_000_000 * .5 * .6 * .1 * .9,
    'illustrative_year_result': 1_000_000 * .5 * .6 * .1 * .9 * 40 - 4_200_000,
    'sample_size_per_group_normal_approx': n,
    'sample_size_assumptions': 'Two-sided normal approximation, Bonferroni for 2 comparisons; not power for profit.',
    'twelve_weeks_from_2026_11_11': (date(2026, 11, 11) + timedelta(weeks=12)).isoformat(),
    'last_departure_plus_44_days': (date(2026, 11, 11) + timedelta(weeks=12, days=44)).isoformat(),
    'note': 'Conditional arithmetic only; input values are author assumptions, not measurements or N forecasts.',
}
(HERE / 'chat-answer-audit-calculations.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
