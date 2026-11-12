"""Check visible sentence length, descriptive links and relocated statistical notation."""
from pathlib import Path
import json
import re

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
ROOT = HERE.parents[4]
FILES = [TASK / 'out/summary.md', TASK / 'out/test-plan.md']
LINK = re.compile(r'\[([^\]\n]+)\]\(([^)\n]+)\)')
report = []
failures = []
for path in FILES:
    text = path.read_text(encoding='utf-8')
    links = list(LINK.finditer(text))
    for link in links:
        destination = link[2].split(' "', 1)[0]
        filename, _, anchor = destination.partition('#')
        target = (path.parent / filename).resolve()
        if not target.is_relative_to(ROOT.resolve()) or not target.is_file():
            failures.append(f'{path.name}: missing or external local link {destination}')
        elif anchor:
            headings = re.findall(r'^#{1,6}\s+(.+)$', target.read_text(encoding='utf-8'), re.M)
            anchors = {re.sub(r'[^\w\- ]', '', heading.casefold()).replace(' ', '-') for heading in headings}
            if anchor not in anchors:
                failures.append(f'{path.name}: missing anchor {destination}')
    visible = LINK.sub(lambda match: match[1], text)
    visible = re.sub(r'<!--.*?-->', '', visible, flags=re.S)
    sentences = []
    for number, line in enumerate(visible.splitlines(), 1):
        line = line.strip().replace('**', '').strip('# ')
        if not line or re.fullmatch(r'[| :\-]+', line):
            continue
        line = line.replace('тыс.', 'тыс').replace('млн.', 'млн')
        for sentence in re.split(r'(?<=[.!?])\s+', line):
            for phrase in sentence.split('|'):
                words = phrase.strip().split()
                if words:
                    sentences.append((len(words), number, phrase.strip()))
    for count, number, phrase in sentences:
        if count >= 25:
            failures.append(f'{path.name}:{number}: {count} words: {phrase}')
    service = re.findall(r'\b[SEQOCDK][1-9][0-9]*\b|δ|Δ|r_max|s_max|H0:', visible)
    if service:
        failures.append(f'{path.name}: visible service notation: {service}')
    report.append({'file': path.relative_to(ROOT).as_posix(),
                   'visible_words': len(visible.split()),
                   'max_phrase_words': max((item[0] for item in sentences), default=0),
                   'local_links': len(links), 'visible_service_notation': service})
result = {'files': report, 'failures': failures}
(HERE / 'editorial-readability.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(bool(failures))
