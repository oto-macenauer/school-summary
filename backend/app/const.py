"""Constants for the Bakalari application."""

from typing import Final

# Gemini API constants
GEMINI_API_URL: Final = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODEL: Final = "gemini-2.5-flash-lite"

# Bakalari API constants
API_CLIENT_ID: Final = "ANDR"
API_LOGIN_ENDPOINT: Final = "/api/login"
API_TIMETABLE_ACTUAL: Final = "/api/3/timetable/actual"
API_TIMETABLE_PERMANENT: Final = "/api/3/timetable/permanent"
API_MARKS: Final = "/api/3/marks"
API_MARKS_FINAL: Final = "/api/3/marks/final"
API_MARKS_COUNT_NEW: Final = "/api/3/marks/count-new"
API_KOMENS_RECEIVED: Final = "/api/3/komens/messages/received"
API_KOMENS_SENT: Final = "/api/3/komens/messages/sent"
API_KOMENS_NOTICEBOARD: Final = "/api/3/komens/messages/noticeboard"
API_KOMENS_UNREAD: Final = "/api/3/komens/messages/received/unread"

# Token constants
TOKEN_EXPIRY_BUFFER: Final = 300  # Refresh token 5 minutes before expiry

# Grant types
GRANT_TYPE_PASSWORD: Final = "password"
GRANT_TYPE_REFRESH: Final = "refresh_token"

# Canteen API constants
CANTEEN_API_URL: Final = "https://app.strava.cz/api/jidelnicky"

# Default update intervals (seconds)
DEFAULT_TIMETABLE_UPDATE_INTERVAL: Final = 3600
DEFAULT_MARKS_UPDATE_INTERVAL: Final = 1800
DEFAULT_KOMENS_UPDATE_INTERVAL: Final = 900
DEFAULT_SUMMARY_UPDATE_INTERVAL: Final = 86400
DEFAULT_PREPARE_UPDATE_INTERVAL: Final = 3600
DEFAULT_GDRIVE_UPDATE_INTERVAL: Final = 3600
DEFAULT_CANTEEN_UPDATE_INTERVAL: Final = 3600
DEFAULT_MAIL_UPDATE_INTERVAL: Final = 900
