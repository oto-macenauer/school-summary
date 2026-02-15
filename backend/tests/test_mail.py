"""Tests for the mail module."""

from datetime import datetime

import pytest

from app.modules.mail import MailData, MailMessage


class TestMailMessage:
    def test_from_markdown_full(self):
        content = '---\nsubject: Test Email\nfrom: sender@example.com\ndate: 2025-01-15T10:30:00\n---\n\nHello, this is the email body.'
        msg = MailMessage.from_markdown("file123", content)
        assert msg.file_id == "file123"
        assert msg.subject == "Test Email"
        assert msg.sender == "sender@example.com"
        assert msg.date == datetime(2025, 1, 15, 10, 30)
        assert msg.body == "Hello, this is the email body."

    def test_from_markdown_missing_fields(self):
        content = "---\nsubject: Only Subject\n---\n\nBody text."
        msg = MailMessage.from_markdown("f1", content)
        assert msg.subject == "Only Subject"
        assert msg.sender == "(Unknown sender)"
        assert msg.date is None
        assert msg.body == "Body text."

    def test_from_markdown_no_frontmatter(self):
        content = "Just plain text, no frontmatter."
        msg = MailMessage.from_markdown("f2", content)
        assert msg.subject == "(No subject)"
        assert msg.sender == "(Unknown sender)"
        assert msg.body == "Just plain text, no frontmatter."

    def test_from_markdown_invalid_date(self):
        content = "---\nsubject: Bad Date\ndate: not-a-date\n---\n\nBody."
        msg = MailMessage.from_markdown("f3", content)
        assert msg.date is None
        assert msg.subject == "Bad Date"

    def test_from_markdown_quoted_values(self):
        content = '---\nsubject: "Quoted Subject"\nfrom: \'quoted@sender.com\'\n---\n\nBody.'
        msg = MailMessage.from_markdown("f4", content)
        assert msg.subject == "Quoted Subject"
        assert msg.sender == "quoted@sender.com"

    def test_from_markdown_extra_keys_ignored(self):
        content = "---\nsubject: Test\nfrom: a@b.com\nfile_id: old_id\nsynced_at: 2025-01-01\n---\n\nBody."
        msg = MailMessage.from_markdown("new_id", content)
        assert msg.file_id == "new_id"
        assert msg.subject == "Test"

    def test_to_dict(self):
        msg = MailMessage(
            file_id="f1",
            subject="Test",
            sender="a@b.com",
            date=datetime(2025, 1, 15, 10, 0),
            body="Body",
        )
        d = msg.to_dict()
        assert d["id"] == "f1"
        assert d["subject"] == "Test"
        assert d["sender"] == "a@b.com"
        assert d["date"] == "2025-01-15T10:00:00"
        assert d["body"] == "Body"

    def test_to_dict_no_date(self):
        msg = MailMessage(file_id="f1", subject="X", sender="Y", date=None, body="Z")
        assert msg.to_dict()["date"] is None


class TestMailData:
    def test_to_summary_dict_sorted(self):
        msgs = [
            MailMessage("f1", "Old", "a@b.com", datetime(2025, 1, 1), ""),
            MailMessage("f2", "New", "a@b.com", datetime(2025, 1, 15), ""),
        ]
        data = MailData(messages=msgs)
        result = data.to_summary_dict()
        assert result["total_count"] == 2
        assert result["messages"][0]["subject"] == "New"
        assert result["messages"][1]["subject"] == "Old"

    def test_to_summary_dict_none_dates_last(self):
        msgs = [
            MailMessage("f1", "No date", "a@b.com", None, ""),
            MailMessage("f2", "Has date", "a@b.com", datetime(2025, 1, 1), ""),
        ]
        data = MailData(messages=msgs)
        result = data.to_summary_dict()
        assert result["messages"][0]["subject"] == "Has date"
        assert result["messages"][1]["subject"] == "No date"

    def test_empty(self):
        data = MailData()
        result = data.to_summary_dict()
        assert result["total_count"] == 0
        assert result["messages"] == []

    def test_total_count(self):
        msgs = [MailMessage(f"f{i}", f"Sub{i}", "a@b.com", None, "") for i in range(5)]
        data = MailData(messages=msgs)
        assert data.total_count == 5
