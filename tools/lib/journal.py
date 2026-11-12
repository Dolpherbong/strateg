"""Append journal entries and summarize time and cost."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .records import read, visible
from .workspace import within


@dataclass(frozen=True)
class LogEntry:
    """Parameters of one journal entry."""

    action: str
    stage: int
    tool: str
    result: str
    minutes: Decimal | None = None
    tokens: Decimal | None = None
    cost: Decimal | None = None
    approx: bool = False
    key: str = ""
    status: str = "готово"


def number(value: str) -> Decimal:
    """Parse a nonnegative decimal number.

    Args:
        value: Value to validate.

    Returns:
        A finite nonnegative Decimal value.
    """
    try:
        result = Decimal(value.replace(",", "."))
    except InvalidOperation as error:
        raise ValueError(f"Неверное число: {value!r}") from error
    if not result.is_finite() or result < 0:
        raise ValueError(f"Нужно неотрицательное конечное число: {value!r}")
    return result


def _format(value: Decimal | None, approx: bool = False) -> str:
    if value is None:
        return ""
    digits = format(value, "f")
    if "." in digits:
        digits = digits.rstrip("0").rstrip(".")
    return f"{'~' if approx else ''}{digits}"


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "/").split())


def _rows(text: str) -> list[tuple[str, ...]]:
    result = []
    for line in visible(text).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        parts = tuple(part.strip() for part in line.strip().strip("|").split("|"))
        if parts and parts[0].isdigit():
            if len(parts) != 11:
                raise ValueError(f"Битая строка журнала: {parts[0]}")
            result.append(parts)
    if "| № |" not in text or "| статус |" not in text:
        raise ValueError("В журнале нет таблицы установленного формата")
    return result


def append(task: Path, entry: LogEntry) -> tuple[str, bool]:
    """Append a step unless its successful key is already present.

    Args:
        task: Task directory or selected task name.
        entry: Journal entry parameters.

    Returns:
        The journal row and whether the key already succeeded.
    """
    path = within(task, task / "journal.md")
    text = read(path)
    rows, key = _rows(text), _cell(entry.key)
    for row in rows:
        if key and row[9] == key and row[10] == "готово":
            return "| " + " | ".join(row) + " |", True
    if not _cell(entry.action) or not _cell(entry.result):
        raise ValueError("Действие и итог не должны быть пустыми")
    serial = max((int(row[0]) for row in rows), default=0) + 1
    values = (str(serial), datetime.now().strftime("%Y-%m-%d %H:%M"), str(entry.stage),
              _cell(entry.action), _cell(entry.tool), _cell(entry.result),
              _format(entry.minutes, entry.approx), _format(entry.tokens, entry.approx),
              _format(entry.cost, entry.approx), key, entry.status)
    line = "| " + " | ".join(values) + " |"
    newline = "\r\n" if "\r\n" in text else "\n"
    prefix = "" if text.endswith(("\n", "\r")) else newline
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(prefix + line + newline)
    return line, False


def _amount(cell: str) -> tuple[Decimal | None, bool]:
    return (number(cell.lstrip("~")), cell.startswith("~")) if cell else (None, False)


def _row_count(count: int) -> str:
    suffix = "строк"
    if count % 100 not in (11, 12, 13, 14):
        suffix = "строка" if count % 10 == 1 else "строки" if count % 10 in (2, 3, 4) else suffix
    return f"{count} {suffix}"


def _metric(value: Decimal, approx: bool, missing: int, count: int) -> str:
    if count == missing:
        return f"не оценено ({_row_count(missing)})" if missing else "не оценено"
    suffix = f"; не оценено: {_row_count(missing)}" if missing else ""
    return _format(value, approx) + suffix


def _total(rows: list[tuple[str, ...]], price: Decimal | None) -> str:
    sums, estimates, missing = [Decimal(0)] * 3, [False] * 3, [0] * 3
    for row in rows:
        metrics = [_amount(cell) for cell in row[6:9]]
        if metrics[2][0] is None and metrics[1][0] is not None and price is not None:
            metrics[2] = (metrics[1][0] * price, metrics[1][1])
        for position, (value, approx) in enumerate(metrics):
            if value is None:
                missing[position] += 1
            else:
                sums[position] += value
                estimates[position] = estimates[position] or approx
    amounts = [_metric(value, approx, absent, len(rows)) for value, approx, absent in zip(sums, estimates, missing)]
    return f"шагов: {len(rows)}; мин: {amounts[0]}; ток., тыс.: {amounts[1]}; ₽: {amounts[2]}"


def _clock(rows: list[tuple[str, ...]]) -> str:
    stamps = []
    for row in rows:
        try:
            stamps.append(datetime.strptime(row[1], "%Y-%m-%d %H:%M"))
        except ValueError:
            continue
    if len(stamps) < 2:
        return "По часам: меньше двух отметок времени"
    first, last = min(stamps), max(stamps)
    minutes = int((last - first).total_seconds() // 60)
    return f"По часам: с {first:%Y-%m-%d %H:%M} по {last:%Y-%m-%d %H:%M}, {minutes} мин"


def cost(task: Path, price: Decimal | None = None) -> tuple[str, ...]:
    """Summarize journal totals by stage and tool.

    Args:
        task: Task directory or selected task name.
        price: Optional price per thousand tokens.

    Returns:
        Summary lines, marking estimates with a tilde.
    """
    rows = _rows(read(within(task, task / "journal.md")))
    lines = [f"Шагов: {len(rows)}", f"Всего: {_total(rows, price)}"]
    for column, label in ((2, "Этап"), (4, "Средство")):
        for key in sorted({row[column] for row in rows}):
            group = [row for row in rows if row[column] == key]
            lines.append(f"{label} {key}: {_total(group, price)}")
    lines.append(f"Сбоев: {sum(row[10] == 'сбой' for row in rows)}")
    lines.append(_clock(rows))
    return tuple(lines)
