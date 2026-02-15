"""Storage module for saving Gmail messages to Markdown files."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..modules.mail import MailData, MailMessage

_LOGGER = logging.getLogger("bakalari.mail_storage")


def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    sanitized = name.replace("\n", " ").replace("\r", " ")
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized)
    sanitized = sanitized.strip(". ")
    if len(sanitized) > 80:
        sanitized = sanitized[:80]
    return sanitized or "untitled"


class MailStorage:
    """Handles local storage of Gmail messages as Markdown files."""

    def __init__(self, storage_path: str | Path, student_name: str) -> None:
        self._base_path = Path(storage_path)
        self._student_name = _sanitize_filename(student_name)
        self._student_path = self._base_path / self._student_name
        self._index: dict[str, Path] = {}

    @property
    def storage_path(self) -> Path:
        return self._student_path

    def ensure_directory(self) -> None:
        self._student_path.mkdir(parents=True, exist_ok=True)

    def message_exists(self, file_id: str) -> bool:
        return file_id in self._index

    def _generate_filename(self, msg: MailMessage) -> str:
        date_str = msg.date.strftime("%Y-%m-%d_%H%M%S") if msg.date else "unknown"
        subject_part = _sanitize_filename(msg.subject)[:50]
        return f"{date_str}_{subject_part}.md"

    def save_message(self, msg: MailMessage) -> Path | None:
        """Save a mail message to disk. Returns path or None if already exists."""
        if self.message_exists(msg.file_id):
            return None

        self.ensure_directory()
        path = self._student_path / self._generate_filename(msg)

        metadata = [
            "---",
            f"file_id: {msg.file_id}",
            f'subject: "{msg.subject}"',
            f'from: "{msg.sender}"',
            f'date: "{msg.date.isoformat() if msg.date else ""}"',
            f'synced_at: "{datetime.now().isoformat()}"',
            "---",
            "",
            msg.body,
        ]
        content = "\n".join(metadata)

        try:
            path.write_text(content, encoding="utf-8")
            self._index[msg.file_id] = path
            _LOGGER.info("Saved mail: %s", path.name)
            return path
        except OSError as err:
            _LOGGER.error("Failed to save mail %s: %s", msg.subject, err)
            return None

    def save_messages(self, messages: list[MailMessage]) -> int:
        """Save multiple messages, returns count of newly saved."""
        saved = 0
        for msg in messages:
            if self.save_message(msg):
                saved += 1
        return saved

    def load_index(self) -> None:
        """Rebuild the in-memory index from files on disk."""
        self._index.clear()
        if not self._student_path.exists():
            return
        for md_file in self._student_path.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                match = re.search(r"file_id:\s*(.+)", content)
                if match:
                    self._index[match.group(1).strip()] = md_file
            except OSError as err:
                _LOGGER.warning("Failed to read %s: %s", md_file, err)

    def load_all_messages(self) -> MailData:
        """Load all stored messages from disk into MailData."""
        messages: list[MailMessage] = []
        if not self._student_path.exists():
            return MailData(messages=[])

        for md_file in self._student_path.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                match = re.search(r"file_id:\s*(.+)", content)
                file_id = match.group(1).strip() if match else md_file.stem
                msg = MailMessage.from_markdown(file_id, content)
                messages.append(msg)
            except Exception as err:
                _LOGGER.warning("Failed to parse mail file %s: %s", md_file, err)

        return MailData(messages=messages)

    def get_statistics(self) -> dict[str, Any]:
        files = list(self._student_path.glob("*.md")) if self._student_path.exists() else []
        total_size = sum(f.stat().st_size for f in files)
        return {
            "storage_path": str(self._student_path),
            "message_count": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }
