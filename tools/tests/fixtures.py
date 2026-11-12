"""Build isolated sample projects using only the standard library."""

from pathlib import Path
import shutil


def write(path: Path, text: str) -> None:
    """Write a sample UTF-8 file.

    Args:
        path: File path.
        text: Source Markdown text.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def record(number: str, **fields: str) -> str:
    """Build a Markdown record from fields.

    Args:
        number: Record identifier.
        fields: Record field values.

    Returns:
        Record text with a heading.
    """
    return f"### {number}\n" + "".join(f"- {k}: {v}\n" for k, v in fields.items()) + "\n"


def prepare(root: Path) -> None:
    """Copy real templates into an isolated sample root.

    Args:
        root: Repository root.
    """
    source = Path(__file__).resolve().parents[2] / "templates"
    shutil.copytree(source, root / "templates")
    write(root / "projects/ACTIVE.md", "- проект: нет\n- задача: нет\n")


def clean(root: Path) -> Path:
    """Create a complete clean sample project with all record types.

    Args:
        root: Repository root.

    Returns:
        The sample task path.
    """
    from tools.lib.workspace import create_project, create_task
    create_project(root, "demo")
    task = create_task(root, "demo", "01-test")
    populate(root, task)
    return task


def populate(root: Path, task: Path) -> None:
    """Populate an existing sample task with a complete clean example.

    Args:
        root: Repository root.
        task: Task directory or selected task name.
    """
    project = task.parents[1]
    _registries(project)
    _documents(root, task)
    _options(task)
    write(task / "questions.md", record("Q1", **{
        "вопрос": "Какова цена?", "зачем": "выбор", "что изменит ответ": "вариант",
        "где искать": "сайт", "статус": "открыт"}))


def _registries(project: Path) -> None:
    write(project / "sources.md", record("S1", **{
        "название": "Учебный сайт", "тип": "сайт", "где": "https://example.org",
        "дата источника": "ноябрь 2026", "дата обращения": "2026-11-11",
        "надёжность": "A", "статус": "действует"}))
    write(project / "evidence.md", record("E1", **{
        "текст": "Цена подписки 450 рублей", "вид": "факт", "источник": "S1",
        "место": "блок цен", "цитата": "«450 рублей»", "период": "ноябрь 2026",
        "статус": "действует", "задача": "01-test"}))
    write(project / "decisions.md", record("D1", **{
        "решение": "проверить подписку", "дата": "2026-11-11",
        "кто решил": "руководитель продукта", "выбран вариант": "O3", "основания": "C1",
        "отвергнуто": "остальные", "ответственный": "аналитик", "показатель": "спрос",
        "срок проверки": "2000-01-01", "условие пересмотра": "спроса нет", "статус": "действует"
    }) + record("K1", **{"что": "проверить спрос", "кто": "аналитик", "срок": "2000-01-01",
                        "к решению": "D1", "статус": "открыто"}))


def _documents(root: Path, task: Path) -> None:
    for template in sorted((root / "templates/out").glob("*.md")):
        headings = [line for line in template.read_text(encoding="utf-8").splitlines()
                    if line.startswith("## ")]
        write(task / "out" / template.name,
              "# Учебный документ\n\n" + "\n".join(f"{h}\nУчебное утверждение [E1].\n" for h in headings))
    path = task / "out/situation.md"
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(record("C1", **{"текст": "Цену можно проверить", "опора": "E1",
                     "уверенность": "средняя", "что может опровергнуть": "новая цена",
                     "статус": "действует"}))


def _options(task: Path) -> None:
    path = task / "out/options.md"
    with path.open("a", encoding="utf-8", newline="") as stream:
        for index, role in enumerate(("статус-кво", "закрыть", "активный"), 1):
            stream.write(record(f"O{index}", **{
                "роль": role, "суть": "учебный вариант [C1]", "что должно быть правдой": "цена [E1]",
                "выгоды": "знания", "цена и риски": "время", "возражение": "спрос неизвестен",
                "ответ на возражение": "проверим", "чего не знаем": "спрос",
                "дешёвая проверка": "сравнить"}))


def _extra_break(task: Path, code: str) -> bool:
    project = task.parents[1]
    if code == "V08":
        path = project / "evidence.md"
        write(path, path.read_text(encoding="utf-8") + record("E8", **{
            "текст": "спрос пока неизвестен", "вид": "гипотеза", "период": "2026",
            "статус": "действует", "задача": "01-test", "как проверить": "опрос"}))
        path = task / "out/situation.md"
        write(path, path.read_text(encoding="utf-8").replace("- опора: E1", "- опора: E8"))
        return True
    if code in ("V04", "V05"):
        path = project / "evidence.md"
        extra = {"текст": "учебное нарушение", "период": "2026", "статус": "действует", "задача": "01-test"}
        extra.update({"вид": "гипотеза"} if code == "V04" else
                     {"вид": "прогноз", "источник": "C1", "срок прогноза": "2027"})
        write(path, path.read_text(encoding="utf-8") + record("E2" if code == "V04" else "E3", **extra))
        return True
    return False


def break_rule(task: Path, code: str) -> None:
    """Introduce an independent violation of the selected gate.

    Args:
        task: Task directory or selected task name.
        code: Validation gate code from V01 through V12.
    """
    if _extra_break(task, code):
        return
    project = task.parents[1]
    changes = {
        "V01": (project / "evidence.md", "- текст: Цена", "- текст: [E999] Цена"),
        "V02": (project / "sources.md", "2026-11-11", "2026-02-30"),
        "V03": (project / "evidence.md", "- цитата: «450 рублей»", "- цитата:"),
        "V06": (project / "sources.md", "- тип: сайт", "- тип: модель"),
        "V07": (project / "sources.md", "- статус: действует", "- статус: отозвано"),
        "V09": (task / "out/options.md", "- роль: закрыть", "- роль: активный"),
        "V10": (task / "out/summary.md", "## Вопрос", "## Другой вопрос"),
        "V11": (task / "out/test-plan.md", "Учебное утверждение [E1].", "Без основания."),
        "V12": (task / "STATE.md", "- этап: 1", "- этап:"),
    }
    path, old, new = changes[code]
    write(path, path.read_text(encoding="utf-8").replace(old, new, 1))


def broken(root: Path) -> Path:
    """Create a sample project violating all twelve gates.

    Args:
        root: Repository root.

    Returns:
        The invalid sample task path.
    """
    task = clean(root)
    for number in range(1, 13):
        break_rule(task, f"V{number:02}")
    return task
