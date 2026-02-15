"""Sync Gmail markdown files from Google Drive to local storage."""

from __future__ import annotations

import logging

from ..core.gdrive import GDRIVE_FILES_ENDPOINT, GoogleDriveClient
from ..modules.mail import MailMessage
from ..storage.mail_storage import MailStorage

_LOGGER = logging.getLogger("bakalari.mail_sync")


async def sync_mail_from_gdrive(
    gdrive_client: GoogleDriveClient,
    mail_folder_id: str,
    mail_storage: MailStorage,
) -> int:
    """Fetch new markdown mail files from Google Drive and save to local storage.

    Returns the count of newly synced messages.
    """
    query = f"'{mail_folder_id}' in parents and trashed = false"
    params = {
        "q": query,
        "fields": "files(id, name, mimeType)",
        "pageSize": "200",
        "orderBy": "createdTime desc",
    }

    response = await gdrive_client._api_request("GET", GDRIVE_FILES_ENDPOINT, params=params)
    if response.status != 200:
        text = await response.text()
        _LOGGER.error("Failed to list mail files (%d): %s", response.status, text)
        return 0

    files = (await response.json()).get("files", [])
    synced = 0

    for file_info in files:
        file_id = file_info["id"]
        file_name = file_info.get("name", "")
        mime_type = file_info.get("mimeType", "")

        if not (file_name.endswith(".md") or mime_type == "text/plain"):
            continue

        if mail_storage.message_exists(file_id):
            continue

        try:
            content = await gdrive_client._get_file_content(file_id, mime_type)
            msg = MailMessage.from_markdown(file_id, content)
            if mail_storage.save_message(msg):
                synced += 1
        except Exception as err:
            _LOGGER.warning("Failed to sync mail file %s (%s): %s", file_name, file_id, err)

    if synced:
        _LOGGER.info("Synced %d new mail messages", synced)

    return synced
