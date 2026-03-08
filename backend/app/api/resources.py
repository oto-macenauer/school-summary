"""Unified resources endpoint with tag support."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter

from ..dependencies import get_student_or_404
from ..storage.tag_storage import TagStorage

router = APIRouter(tags=["resources"])


def _parse_resource_from_file(
    path: Path, category: str,
) -> dict[str, Any] | None:
    """Parse a markdown file into a resource item dict with tags."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm = TagStorage.parse_frontmatter(content)

    item_id = (
        fm.get("message_id")
        or fm.get("file_id")
        or fm.get("week_number")
        or path.stem
    )
    title = fm.get("title") or fm.get("subject") or path.stem
    sender = fm.get("sender") or fm.get("from") or fm.get("school_year") or None
    date_str = fm.get("date") or fm.get("fetched_at") or None

    # Extract body (content after frontmatter)
    parts = content.split("---", 2)
    body = parts[2].strip() if len(parts) >= 3 else content.strip()

    # Read tags
    tags = TagStorage.read_tags(path)
    tags_dict = tags.to_dict() if tags else None

    is_read = None
    raw_read = fm.get("read")
    if raw_read is not None:
        is_read = raw_read.lower() == "true"

    is_markdown = category == "report"

    return {
        "id": f"{category}-{item_id}",
        "category": category,
        "title": title,
        "sender": sender,
        "date": date_str,
        "body": body,
        "isRead": is_read,
        "isMarkdown": is_markdown,
        "tags": tags_dict,
    }


@router.get("/api/students/{name}/resources")
async def get_resources(name: str):
    """Get all resources (komens, mail, reports) with tags for a student."""
    ctx = get_student_or_404(name)
    items: list[dict[str, Any]] = []
    available_tags: dict[str, set[str]] = {"subjects": set(), "importance": set()}

    # Read komens from storage
    for md_file in ctx.komens_storage.get_saved_files():
        item = _parse_resource_from_file(md_file, "komens")
        if item:
            items.append(item)
            if item.get("tags"):
                available_tags["subjects"].update(item["tags"].get("subjects", []))
                available_tags["importance"].update(item["tags"].get("importance", []))

    # Read mail from storage
    mail_path = ctx.mail_storage.storage_path
    if mail_path.exists():
        for md_file in mail_path.glob("*.md"):
            item = _parse_resource_from_file(md_file, "mail")
            if item:
                items.append(item)
                if item.get("tags"):
                    available_tags["subjects"].update(item["tags"].get("subjects", []))
                    available_tags["importance"].update(item["tags"].get("importance", []))

    # Read gdrive reports
    for md_file in ctx.gdrive_storage.get_all_reports():
        item = _parse_resource_from_file(md_file, "report")
        if item:
            items.append(item)
            if item.get("tags"):
                available_tags["subjects"].update(item["tags"].get("subjects", []))
                available_tags["importance"].update(item["tags"].get("importance", []))

    # Sort by date descending
    items.sort(key=lambda x: x.get("date") or "", reverse=True)

    return {
        "items": items,
        "available_tags": {
            "subjects": sorted(available_tags["subjects"]),
            "importance": sorted(available_tags["importance"]),
        },
    }
