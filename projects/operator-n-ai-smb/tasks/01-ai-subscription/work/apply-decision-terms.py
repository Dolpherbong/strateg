"""Точечный пересмотр ссылок после решения S13, без правки исходных материалов."""
import re
from pathlib import Path

TASK = Path(__file__).resolve().parent.parent
PROJECT = TASK.parent.parent
REPLACEMENTS = {"E37": "E51", "E40": "E52", "E45": "E53", "E36": "E54"}


def supersede(text, old, new):
    pattern = rf"(^### {old}\b[^\n]*\n)(.*?)(?=^#{{1,3}} |\Z)"

    def replace(match):
        body = match.group(2)
        if "- статус: устарело\n" in body:
            if f"- заменено: {new}\n" not in body:
                raise ValueError(f"Unexpected replacement: {old}")
            return match.group(0)
        if body.count("- статус: действует\n") != 1:
            raise ValueError(f"Unexpected status: {old}")
        return match.group(1) + body.replace(
            "- статус: действует\n", f"- статус: устарело\n- заменено: {new}\n", 1
        )

    result, count = re.subn(pattern, replace, text, flags=re.M | re.S)
    if count != 1:
        raise ValueError(f"Expected one record: {old}")
    return result


def update_links(text):
    def replace(match):
        return re.sub(r"\b(E37|E40|E45|E36)\b", lambda item: REPLACEMENTS[item.group(0)], match.group(0))
    return re.sub(r"\[[^\]\n]+\]", replace, text)


def main():
    path = PROJECT / "evidence.md"
    text = path.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS.items():
        text = supersede(text, old, new)
    path.write_text(text, encoding="utf-8")

    paths = list((TASK / "out").glob("*.md"))
    paths += [TASK / "work" / name for name in (
        "core.md", "test-protocol.md", "test-budget.md", "strategy-economics.py", "strategy-economics.md"
    )]
    for path in paths:
        text = update_links(path.read_text(encoding="utf-8"))
        if path.parent.name == "out":
            text = re.sub(r"^- пересмотрено: .*", "- пересмотрено: 2026-11-12, S13", text, flags=re.M)
        path.write_text(text, encoding="utf-8")
    print("Updated evidence status and current document links; inbox untouched.")


if __name__ == "__main__":
    main()
