"""Provider-independent CRM validation, clock and catalog helpers."""
from datetime import datetime, timezone
from email.utils import parseaddr
from zoneinfo import ZoneInfo
import re

USER_COLUMNS = ["user_name", "name", "role", "email", "phone", "password", "active", "admin"]
SETTINGS_COLUMNS = ["key", "value", "description"]
STOCKHOLM_TIMEZONE = ZoneInfo("Europe/Stockholm")

def is_yes(value):
    return str(value or "").strip().casefold() in {"y", "yes", "ja", "1", "true", "on"}


def normalize_email(value):
    return str(value or "").strip().casefold()


def is_valid_email(value):
    text = str(value or "").strip()
    if not text or len(text) > 254 or "\n" in text or "\r" in text:
        return False
    _, address = parseaddr(text)
    if address != text or address.count("@") != 1:
        return False
    local, domain = address.rsplit("@", 1)
    return bool(local and "." in domain and not domain.startswith(".") and not domain.endswith("."))


def split_email_values(*values):
    result = []
    seen = set()
    for value in values:
        for candidate in re.split(r"[,;\n\r]+", str(value or "")):
            email = candidate.strip()
            key = normalize_email(email)
            if not key or key in seen:
                continue
            seen.add(key)
            result.append({"email": email, "valid": is_valid_email(email)})
    return result






def stockholm_now():
    return datetime.now(STOCKHOLM_TIMEZONE)


def stockholm_today():
    return stockholm_now().date()


def stockholm_time_text(value=None):
    """Return a stable local timestamp for Sheets, regardless of source timezone."""
    if value is None or value == "":
        parsed = stockholm_now()
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        try:
            parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            parsed = stockholm_now()
    else:
        text = str(value).strip()
        if not text:
            parsed = stockholm_now()
        else:
            iso_text = text.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(iso_text)
            except ValueError:
                parsed = None
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        parsed = datetime.strptime(text, fmt)
                        break
                    except ValueError:
                        pass
                if parsed is None:
                    parsed = stockholm_now()

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=STOCKHOLM_TIMEZONE)
    else:
        parsed = parsed.astimezone(STOCKHOLM_TIMEZONE)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


