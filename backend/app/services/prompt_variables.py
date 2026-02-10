"""Variable resolver for custom AI prompts."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

from ..services.student_manager import StudentContext

_LOGGER = logging.getLogger("bakalari.prompt_variables")

_VAR_PATTERN = re.compile(r"\{([^{}]+)\}")


def resolve_prompt(prompt: str, ctx: StudentContext) -> tuple[str, list[str]]:
    """Resolve all {variable} references in a prompt string.

    Returns the resolved prompt and a list of variable names that were resolved.
    """
    resolved: list[str] = []

    def _replacer(match: re.Match) -> str:
        expr = match.group(1).strip()
        value = _resolve_variable(expr, ctx)
        if value is not None:
            resolved.append(expr)
            return value
        # Leave unresolved variables as-is
        return match.group(0)

    result = _VAR_PATTERN.sub(_replacer, prompt)
    return result, resolved


def _resolve_variable(expr: str, ctx: StudentContext) -> str | None:
    """Resolve a single variable expression like 'marks:cj' or 'komens:last:10'."""
    parts = expr.split(":")
    category = parts[0].lower().strip()
    params = [p.strip() for p in parts[1:]]

    resolvers = {
        "timetable": _resolve_timetable,
        "marks": _resolve_marks,
        "komens": _resolve_komens,
        "gdrive": _resolve_gdrive,
        "summary": _resolve_summary,
        "prepare": _resolve_prepare,
        "student_info": _resolve_student_info,
    }

    resolver = resolvers.get(category)
    if resolver is None:
        return None

    try:
        return resolver(params, ctx)
    except Exception as err:
        _LOGGER.warning("Failed to resolve variable '%s': %s", expr, err)
        return f"[Chyba při načítání {expr}]"


def _resolve_timetable(params: list[str], ctx: StudentContext) -> str:
    if not params:
        return ctx.summary_module.format_timetable(ctx.timetable)

    param = params[0].lower()
    if param == "today":
        text, _ = ctx.prepare_module.format_lessons(ctx.timetable, date.today())
        return text
    if param == "tomorrow":
        text, _ = ctx.prepare_module.format_lessons(
            ctx.timetable, date.today() + timedelta(days=1),
        )
        return text

    return ctx.summary_module.format_timetable(ctx.timetable)


def _resolve_marks(params: list[str], ctx: StudentContext) -> str:
    marks_data = ctx.marks
    if marks_data is None:
        return "Žádné známky nejsou k dispozici."

    if not params:
        return _format_all_marks(marks_data)

    param = params[0].lower()

    if param == "new":
        return _format_new_marks(marks_data)

    # Subject filter — match by name or abbreviation (case-insensitive)
    subject_name = params[0]
    for subject in marks_data.subjects:
        if (
            subject.subject_name.lower() == subject_name.lower()
            or subject.subject_abbrev.lower() == subject_name.lower()
        ):
            return _format_subject_marks(subject)

    return f"Předmět '{subject_name}' nenalezen."


def _format_all_marks(marks_data: MarksData) -> str:
    lines: list[str] = []
    for subject in marks_data.subjects:
        avg = f" (průměr: {subject.average_text})" if subject.average_text else ""
        marks_text = ", ".join(
            f"{m.mark_text} ({m.caption})" for m in sorted(
                subject.marks,
                key=lambda m: m.mark_date or datetime.min,
                reverse=True,
            )[:10]
        )
        lines.append(f"- {subject.subject_name}{avg}: {marks_text or 'žádné známky'}")
    return "\n".join(lines) if lines else "Žádné známky."


def _format_new_marks(marks_data: MarksData) -> str:
    lines: list[str] = []
    for subject in marks_data.subjects:
        new = [m for m in subject.marks if m.is_new]
        if new:
            marks_text = ", ".join(f"{m.mark_text} ({m.caption})" for m in new)
            lines.append(f"- {subject.subject_name}: {marks_text}")
    return "\n".join(lines) if lines else "Žádné nové známky."


def _format_subject_marks(subject) -> str:
    avg = f"Průměr: {subject.average_text}\n" if subject.average_text else ""
    marks_text = "\n".join(
        f"- [{m.mark_date.strftime('%d.%m.%Y') if m.mark_date else '?'}] "
        f"{m.mark_text} - {m.caption} (váha: {m.weight})"
        for m in sorted(
            subject.marks,
            key=lambda m: m.mark_date or datetime.min,
            reverse=True,
        )
    )
    return f"{subject.subject_name}\n{avg}{marks_text or 'Žádné známky.'}"


def _resolve_komens(params: list[str], ctx: StudentContext) -> str:
    if not params:
        messages = ctx.summary_module.get_recent_messages(days_back=30)
        return ctx.summary_module.format_messages(messages[:20])

    param = params[0].lower()

    if param == "unread":
        if ctx.komens is None:
            return "Žádné zprávy."
        unread = [m for m in ctx.komens.received if not m.is_read]
        if not unread:
            return "Žádné nepřečtené zprávy."
        return "\n".join(
            f"- [{m.sent_date.strftime('%d.%m.%Y %H:%M') if m.sent_date else '?'}] "
            f"{m.title} (od: {m.sender.name if m.sender else '?'}):\n  {m.plain_text[:500]}"
            for m in unread[:20]
        )

    if param == "last" and len(params) >= 2:
        try:
            count = int(params[1])
        except ValueError:
            count = 20
        messages = ctx.summary_module.get_recent_messages(days_back=365)
        return ctx.summary_module.format_messages(messages[:count])

    return ctx.summary_module.format_messages(
        ctx.summary_module.get_recent_messages(days_back=30)[:20],
    )


def _resolve_gdrive(params: list[str], ctx: StudentContext) -> str:
    if not params:
        return ctx.gdrive_storage.get_latest_report() or "Žádný GDrive report."

    param = params[0].lower()

    if param == "latest":
        return ctx.gdrive_storage.get_latest_report() or "Žádný GDrive report."

    if param == "current":
        from ..core.gdrive import get_school_week_number, get_school_year_start

        school_start = get_school_year_start()
        week_num = get_school_week_number(date.today(), school_start)
        return ctx.gdrive_storage.get_report(week_num) or f"Report pro týden {week_num} není k dispozici."

    # wN format (e.g. w10, w5)
    match = re.match(r"^w(\d+)$", param)
    if match:
        week_num = int(match.group(1))
        return ctx.gdrive_storage.get_report(week_num) or f"Report pro týden {week_num} není k dispozici."

    return "Neznámý parametr pro gdrive."


def _resolve_summary(params: list[str], ctx: StudentContext) -> str:
    if not params:
        param = "current"
    else:
        param = params[0].lower()

    mapping = {
        "current": ctx.summary_current,
        "last": ctx.summary_last,
        "next": ctx.summary_next,
    }

    data = mapping.get(param)
    if data is None:
        return f"Shrnutí ({param}) není k dispozici."
    return data.summary_text


def _resolve_prepare(params: list[str], ctx: StudentContext) -> str:
    if not params:
        param = "tomorrow"
    else:
        param = params[0].lower()

    mapping = {
        "today": ctx.prepare_today,
        "tomorrow": ctx.prepare_tomorrow,
    }

    data = mapping.get(param)
    if data is None:
        return f"Příprava ({param}) není k dispozici."
    return data.preparation_text


def _resolve_student_info(params: list[str], ctx: StudentContext) -> str:
    return ctx.student_info or "Žádné doplňující informace o studentovi."


def get_available_variables(ctx: StudentContext) -> list[dict[str, str]]:
    """Return list of available variables with descriptions."""
    variables: list[dict[str, str]] = [
        {"name": "timetable", "category": "timetable", "description": "Celý týdenní rozvrh"},
        {"name": "timetable:today", "category": "timetable", "description": "Dnešní rozvrh"},
        {"name": "timetable:tomorrow", "category": "timetable", "description": "Zítřejší rozvrh"},
        {"name": "marks", "category": "marks", "description": "Všechny známky se průměry"},
        {"name": "marks:new", "category": "marks", "description": "Pouze nové známky"},
        {"name": "komens", "category": "komens", "description": "Posledních 20 zpráv"},
        {"name": "komens:unread", "category": "komens", "description": "Nepřečtené zprávy"},
        {"name": "komens:last:10", "category": "komens", "description": "Posledních 10 zpráv"},
        {"name": "komens:last:30", "category": "komens", "description": "Posledních 30 zpráv"},
        {"name": "gdrive:current", "category": "gdrive", "description": "Report aktuálního týdne"},
        {"name": "gdrive:latest", "category": "gdrive", "description": "Nejnovější report"},
        {"name": "summary:current", "category": "summary", "description": "Shrnutí aktuálního týdne"},
        {"name": "summary:last", "category": "summary", "description": "Shrnutí minulého týdne"},
        {"name": "summary:next", "category": "summary", "description": "Shrnutí příštího týdne"},
        {"name": "prepare:today", "category": "prepare", "description": "Příprava na dnešek"},
        {"name": "prepare:tomorrow", "category": "prepare", "description": "Příprava na zítřek"},
        {"name": "student_info", "category": "student_info", "description": "Informace o studentovi (třída, třídní učitel apod.)"},
    ]

    # Add subject-specific marks variables
    if ctx.marks:
        for subject in ctx.marks.subjects:
            variables.append({
                "name": f"marks:{subject.subject_abbrev.lower()}",
                "category": "marks",
                "description": f"Známky z předmětu {subject.subject_name}",
            })

    # Add available gdrive week reports
    reports = ctx.gdrive_storage.get_all_reports()
    for path in reports[:10]:
        # Extract week number from filename "week_NN.md"
        match = re.search(r"week_(\d+)", path.stem)
        if match:
            week_num = int(match.group(1))
            variables.append({
                "name": f"gdrive:w{week_num}",
                "category": "gdrive",
                "description": f"Report týdne {week_num}",
            })

    return variables
