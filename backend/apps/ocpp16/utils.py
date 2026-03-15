from datetime import datetime, timezone

TIMESTAMP_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
]


def parse_ocpp_timestamp(ts: str) -> datetime:
    """Parse an OCPP timestamp string to a UTC-aware datetime."""
    for fmt in TIMESTAMP_FORMATS:
        try:
            dt = datetime.strptime(ts, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Cannot parse OCPP timestamp: {ts!r}")


def utcnow_iso() -> str:
    """Return current UTC time in OCPP timestamp format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
