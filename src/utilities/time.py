from datetime import datetime, timezone


def get_utcnow():
    return datetime.now(tz=timezone.utc)
