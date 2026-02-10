"""Storage module for saving Komens messages to Markdown files."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..modules.komens import Message, MessagesData

_LOGGER = logging.getLogger("bakalari.komens_storage")


def sanitize_filename(name: str) -> str:
    sanitized = name.replace("\n", " ").replace("\r", " ")
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", sanitized)
    sanitized = re.sub(r'\s+', ' ', sanitized)
    sanitized = sanitized.strip(". ")
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    return sanitized or "untitled"


class KomensStorage:
    """Handles storage of Komens messages to Markdown files."""

    def __init__(self, storage_path: str | Path, student_name: str) -> None:
        self._base_path = Path(storage_path)
        self._student_name = sanitize_filename(student_name)
        self._student_path = self._base_path / self._student_name
        self._index: dict[str, str] = {}

    @property
    def storage_path(self) -> Path:
        return self._student_path

    def ensure_directory(self) -> None:
        self._student_path.mkdir(parents=True, exist_ok=True)

    def _generate_filename(self, message: Message) -> str:
        date_str = "unknown"
        if message.sent_date:
            date_str = message.sent_date.strftime("%Y-%m-%d_%H%M%S")
        title_part = sanitize_filename(message.title)[:50]
        return f"{date_str}_{title_part}.md"

    def _get_message_path(self, message: Message) -> Path:
        return self._student_path / self._generate_filename(message)

    def message_exists(self, message: Message) -> bool:
        if message.message_id in self._index:
            return True
        return self._get_message_path(message).exists()

    def save_message(self, message: Message, overwrite: bool = False) -> Path | None:
        self.ensure_directory()
        if not overwrite and self.message_exists(message):
            return None
        path = self._get_message_path(message)
        content = message.to_markdown()
        metadata = [
            "---",
            f"message_id: {message.message_id}",
            f"title: {message.title}",
            f"sender: {message.sender.name if message.sender else 'Unknown'}",
            f"date: {message.sent_date.isoformat() if message.sent_date else 'Unknown'}",
            f"type: {message.message_type}",
            f"read: {message.is_read}",
            f"confirmed: {message.is_confirmed}",
            f"saved_at: {datetime.now().isoformat()}",
            "---",
            "",
        ]
        full_content = "\n".join(metadata) + content
        try:
            path.write_text(full_content, encoding="utf-8")
            self._index[message.message_id] = str(path)
            _LOGGER.info("Saved message: %s", path)
            return path
        except OSError as err:
            _LOGGER.error("Failed to save message %s: %s", message.title, err)
            return None

    def save_messages(self, messages: list[Message], overwrite: bool = False) -> list[Path]:
        saved = []
        for message in messages:
            path = self.save_message(message, overwrite=overwrite)
            if path:
                saved.append(path)
        return saved

    def save_all_messages(self, messages_data: MessagesData, overwrite: bool = False) -> dict[str, list[Path]]:
        return {
            "received": self.save_messages(messages_data.received, overwrite),
            "noticeboard": self.save_messages(messages_data.noticeboard, overwrite),
            "sent": self.save_messages(messages_data.sent, overwrite),
        }

    def load_index(self) -> None:
        self._index.clear()
        if not self._student_path.exists():
            return
        for md_file in self._student_path.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                match = re.search(r"message_id:\s*(.+)", content)
                if match:
                    self._index[match.group(1).strip()] = str(md_file)
            except OSError as err:
                _LOGGER.warning("Failed to read %s: %s", md_file, err)

    def get_saved_message_ids(self) -> set[str]:
        self.load_index()
        return set(self._index.keys())

    def get_saved_files(self) -> list[Path]:
        if not self._student_path.exists():
            return []
        return list(self._student_path.glob("*.md"))

    def get_statistics(self) -> dict[str, Any]:
        files = self.get_saved_files()
        total_size = sum(f.stat().st_size for f in files)
        return {
            "storage_path": str(self._student_path),
            "message_count": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }
