"""Записать подтверждённое решение и сроки после сообщения S14."""
import calendar
from datetime import date, timedelta
from pathlib import Path
import re

TASK = Path(__file__).resolve().parent.parent
PROJECT = TASK.parent.parent
START = date(2026, 12, 1)
EARLY = START + timedelta(days=14)
INTERIM = START + timedelta(days=56)
month_index = START.year * 12 + START.month - 1 + 3
year, month0 = divmod(month_index, 12)
FINAL = date(year, month0 + 1, min(START.day, calendar.monthrange(year, month0 + 1)[1]))
MAP = {"E50": "E57", "E54": "E58"}


def current_links(text):
    return re.sub(r"\[[^\]\n]+\]", lambda m: re.sub(r"\b(E50|E54)\b", lambda n: MAP[n.group(0)], m.group(0)), text)


def supersede(text, old, new):
    def replace(match):
        block = match.group(0)
        if "- статус: устарело\n" in block and f"- заменено: {new}\n" in block:
            return block
        if block.count("- статус: действует\n") != 1:
            raise ValueError(f"Unexpected status {old}")
        return block.replace("- статус: действует\n", f"- статус: устарело\n- заменено: {new}\n", 1)
    result, count = re.subn(rf"^### {old}\b[^\n]*\n.*?(?=^#{{1,3}} |\Z)", replace, text, flags=re.M | re.S)
    if count != 1:
        raise ValueError(f"Expected one {old}")
    return result


def main():
    ledger_path = PROJECT / "decisions.md"
    ledger = ledger_path.read_text(encoding="utf-8")
    # Игнорируем формы в комментариях: живые номера должны быть свободны.
    live = re.sub(r"<!--.*?-->", "", ledger, flags=re.S)
    if re.search(r"^### (D1|K\d+)\b", live, flags=re.M):
        raise ValueError("Decision or commitment already exists; do not overwrite")
    draft_path = TASK / "work" / "decision-and-commitments.md"
    draft = draft_path.read_text(encoding="utf-8")
    decision = re.search(r"```text\n(### D1\n.*?)\n```", draft, flags=re.S).group(1)
    decision = re.sub(r"^- срок проверки: .*", f"- срок проверки: {FINAL.isoformat()}", decision, flags=re.M)
    decision = re.sub(r"\bE50\b", "E57", decision)
    decision = decision.replace("- основания: E47,", "- основания: E55, E56, E47,")
    decision = decision.replace("по E43", "по [E43]")
    decision += f"\n- плановый старт: {START.isoformat()}\n- календарь: первые оплаты {EARLY}, промежуточный разбор {INTERIM}, масштаб {FINAL} [E56]\n- подтверждение: решение принято человеком [S13], дата старта названа им [S14]; повторного согласия не требуется"
    rows = []
    for line in draft.splitlines():
        if re.match(r"\| K\d+ \|", line):
            columns = [item.strip() for item in line.strip().strip("|").split("|")]
            rows.append(columns)
    if len(rows) != 10:
        raise ValueError("Expected ten prepared commitments")
    commitments = []
    for ident, what, relative, support in rows:
        due = {"K7": EARLY, "K8": INTERIM, "K9": FINAL}.get(ident, START)
        if ident == "K10":
            what = "Подтвердить фактический старт в назначенную дату; при переносе сообщить новую дату и обеспечить пересмотр календаря."
        commitments.append(
            f"### {ident}\n- что: {what}\n- кто: руководитель B2B-продуктов\n"
            f"- срок: {due.isoformat()}\n- к решению: D1\n- статус: открыто\n"
            f"- условие срока: {relative}; дата не отменяет более ранний допуск до действий\n"
            f"- опора: {current_links(support).strip('[]')}"
        )
    ledger = ledger.replace("## Подтверждённое решение от 2026-11-12: календарь ожидает старта", "## История первой фиксации: до уточнения даты источником S14")
    ledger = ledger.replace("Дата старта не названа.", "Прежний статус, до S14: дата старта не названа.", 1)
    ledger = current_links(ledger)
    insertion = "\n## Действующее решение и обязательства\n\n" + decision + "\n\n" + "\n\n".join(commitments) + "\n"
    ledger = ledger.replace("# Решения и обязательства\n", "# Решения и обязательства\n" + insertion, 1)
    ledger_path.write_text(ledger, encoding="utf-8")

    path = PROJECT / "evidence.md"
    evidence = path.read_text(encoding="utf-8")
    for old, new in MAP.items():
        evidence = supersede(evidence, old, new)
    path.write_text(evidence, encoding="utf-8")
    paths = list((TASK / "out").glob("*.md")) + [TASK / "brief.md", TASK / "work" / "test-protocol.md", TASK / "work" / "core.md"]
    for path in paths:
        text = current_links(path.read_text(encoding="utf-8"))
        if path.parent.name == "out":
            text = re.sub(r"^- пересмотрено: .*", "- пересмотрено: 2026-11-12, S14", text, flags=re.M)
        path.write_text(text, encoding="utf-8")
    draft_path.write_text(draft.replace("# Подтверждённое решение и календарь обязательств\n", "# Подтверждённое решение и календарь обязательств\n\n**Оформлено после S14:** действующие [D1, K1, K2, K3, K4, K5, K6, K7, K8, K9, K10] перенесены в decisions.md. Ниже сохранён исторический черновик до уточнения даты.\n", 1), encoding="utf-8")
    lines = ["# Календарь подтверждённого теста", "", "Плановая дата — [E55], расчёт — [E56]. Фактическое исполнение не подтверждено.", "", "| Контрольная точка | Дата |", "|---|---|"]
    for label, value in (("Старт и готовность допуска", START), ("Первые оплаты, T0+14", EARLY), ("Промежуточный разбор, T0+56", INTERIM), ("Решение о масштабе, T0+3 календарных месяца", FINAL)):
        lines.append(f"| {label} | {value.isoformat()} |")
    (TASK / "work" / "calendar.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"D1, K1-K10 saved. Start={START}; early={EARLY}; interim={INTERIM}; scale={FINAL}")


if __name__ == "__main__":
    main()
