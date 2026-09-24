"""Unified resources endpoint with tag support."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from ..dependencies import get_student_or_404
from ..storage.tag_storage import TagStorage

router = APIRouter(tags=["resources"])


def _week_start_date(week_number: int, school_year: str) -> str:
    """Compute the ISO date of the Monday starting a school week.

    school_year is e.g. "2025/2026" — extract start year, derive Sep 1,
    find its Monday, then offset by (week_number - 1) weeks.
    """
    try:
        start_year = int(school_year.split("/")[0])
    except (ValueError, IndexError):
        return ""
    sep1 = date(start_year, 9, 1)
    # Monday of the week containing Sep 1
    monday_offset = -sep1.weekday()  # weekday(): Mon=0
    start_monday = sep1 + timedelta(days=monday_offset)
    week_date = start_monday + timedelta(weeks=week_number - 1)
    return week_date.isoformat()


def _strip_komens_markdown_header(body: str) -> str:
    """Strip the markdown header produced by Message.to_markdown().

    Komens files contain a markdown-formatted header block before the actual
    message text, separated by a ``---`` line.  The header starts with
    ``# Title`` and includes ``**From:**``, ``**Date:**``, etc.
    """
    # The header block ends with a "---" line.  Find the first occurrence of
    # a line that is exactly "---" (possibly with surrounding whitespace).
    parts = re.split(r"^\s*---\s*$", body, maxsplit=1, flags=re.MULTILINE)
    if len(parts) >= 2:
        return parts[1].strip()
    return body.strip()


def _parse_resource_from_file(
    path: Path, category: str,
) -> dict[str, Any] | None:
    """Parse a markdown file into a resource item dict with tags."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm = TagStorage.parse_frontmatter(content)

    # Reports use report_id: a bare week number repeats every school year.
    item_id = (
        fm.get("message_id")
        or fm.get("file_id")
        or fm.get("report_id")
        or fm.get("week_number")
        or path.stem
    )
    title = fm.get("title") or fm.get("subject") or path.stem
    sender = fm.get("sender") or fm.get("from") or fm.get("school_year") or None

    # Compute date: for reports, derive from week_number + school_year
    if category == "report" and fm.get("week_number") and fm.get("school_year"):
        try:
            wn = int(fm["week_number"])
        except ValueError:
            wn = 0
        date_str = _week_start_date(wn, fm["school_year"]) if wn else None
    else:
        date_str = fm.get("date") or None

    # Extract body (content after YAML frontmatter)
    parts = content.split("---", 2)
    body = parts[2].strip() if len(parts) >= 3 else content.strip()

    # For komens messages, strip the markdown header block
    if category == "komens":
        body = _strip_komens_markdown_header(body)

    # Read tags
    tags = TagStorage.read_tags(path)
    tags_dict = tags.to_dict() if tags else None

    is_read = None
    raw_read = fm.get("read")
    if raw_read is not None:
        is_read = raw_read.lower() == "true"

    is_confirmed = None
    raw_confirmed = fm.get("confirmed")
    if raw_confirmed is not None:
        is_confirmed = raw_confirmed.lower() == "true"

    is_markdown = category == "report"

    return {
        "id": f"{category}-{item_id}",
        "category": category,
        "title": title,
        "sender": sender,
        "date": date_str,
        "body": body,
        "isRead": is_read,
        "isConfirmed": is_confirmed,
        "isMarkdown": is_markdown,
        "tags": tags_dict,
    }


# Parsed items keyed by file path; reused while the file's mtime is unchanged.
# The endpoint pages over every stored file, so re-reading them all on each
# scroll would dominate the request.
_parse_cache: dict[Path, tuple[float, dict[str, Any]]] = {}

CATEGORIES = ("komens", "mail", "report")
MAX_LIMIT = 100


def _parse_cached(path: Path, category: str) -> dict[str, Any] | None:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _parse_cache.pop(path, None)
        return None
    cached = _parse_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    item = _parse_resource_from_file(path, category)
    if item:
        _parse_cache[path] = (mtime, item)
    return item


def collect_resources(ctx: Any) -> list[dict[str, Any]]:
    """All stored resources of a student, newest first."""
    sources: list[tuple[str, list[Path]]] = [
        ("komens", ctx.komens_storage.get_saved_files()),
    ]
    mail_path = ctx.mail_storage.storage_path
    sources.append(("mail", list(mail_path.glob("*.md")) if mail_path.exists() else []))
    sources.append(("report", ctx.gdrive_storage.get_all_reports()))

    items: list[dict[str, Any]] = []
    for category, files in sources:
        for md_file in files:
            item = _parse_cached(md_file, category)
            if item:
                items.append(item)

    items.sort(key=lambda x: x.get("date") or "", reverse=True)
    return items


def _matches(
    item: dict[str, Any],
    importance: str | None,
    subject: str | None,
    query: str,
) -> bool:
    tags = item.get("tags") or {}
    if importance and importance not in tags.get("importance", []):
        return False
    if subject and subject not in tags.get("subjects", []):
        return False
    if query:
        haystack = " ".join(
            str(item.get(k) or "") for k in ("title", "sender", "body")
        ).lower()
        if query not in haystack:
            return False
    return True


@router.get("/api/students/{name}/resources")
async def get_resources(
    name: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=MAX_LIMIT),
    category: str | None = None,
    importance: str | None = None,
    subject: str | None = None,
    q: str | None = None,
):
    """One page of resources (komens, mail, reports) with tags for a student.

    Filters apply before paging. ``counts`` are per category under the tag and
    search filters, so the category pills show what each would list.
    """
    ctx = get_student_or_404(name)
    items = collect_resources(ctx)

    available_tags: dict[str, set[str]] = {"subjects": set(), "importance": set()}
    for item in items:
        if item.get("tags"):
            available_tags["subjects"].update(item["tags"].get("subjects", []))
            available_tags["importance"].update(item["tags"].get("importance", []))

    query = (q or "").strip().lower()
    matching = [i for i in items if _matches(i, importance, subject, query)]
    counts = {"all": len(matching), **{c: 0 for c in CATEGORIES}}
    for item in matching:
        counts[item["category"]] = counts.get(item["category"], 0) + 1

    if category and category != "all":
        matching = [i for i in matching if i["category"] == category]

    page = matching[offset:offset + limit]
    return {
        "items": page,
        "total": len(matching),
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(page) < len(matching),
        "counts": counts,
        "unread_count": sum(
            1 for i in items if i["category"] == "komens" and i.get("isRead") is False
        ),
        "available_tags": {
            "subjects": sorted(available_tags["subjects"]),
            "importance": sorted(available_tags["importance"]),
        },
    }
