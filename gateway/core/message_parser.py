import json
from dataclasses import dataclass

# OCPP-J message type constants
CALL = 2
CALL_RESULT = 3
CALL_ERROR = 4


@dataclass
class OcppMessage:
    msg_type: int
    msg_id: str
    action: str | None  # Only for CALL
    payload: dict


def parse(raw: str) -> OcppMessage:
    """Parse a raw OCPP-J JSON string into an OcppMessage."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")

    if not isinstance(data, list):
        raise ValueError("OCPP message must be a JSON array")

    if len(data) < 3:
        raise ValueError(f"OCPP message array too short: length={len(data)}")

    msg_type = data[0]

    if msg_type == CALL:
        if len(data) < 4:
            raise ValueError("CALL message must have 4 elements: [2, msgId, action, payload]")
        return OcppMessage(
            msg_type=CALL,
            msg_id=str(data[1]),
            action=str(data[2]),
            payload=data[3] if isinstance(data[3], dict) else {},
        )
    elif msg_type == CALL_RESULT:
        return OcppMessage(
            msg_type=CALL_RESULT,
            msg_id=str(data[1]),
            action=None,
            payload=data[2] if isinstance(data[2], dict) else {},
        )
    elif msg_type == CALL_ERROR:
        # [4, msgId, errorCode, errorDescription, errorDetails]
        error_code = data[2] if len(data) > 2 else "GenericError"
        description = data[3] if len(data) > 3 else ""
        details = data[4] if len(data) > 4 else {}
        return OcppMessage(
            msg_type=CALL_ERROR,
            msg_id=str(data[1]),
            action=None,
            payload={"errorCode": error_code, "errorDescription": description, "errorDetails": details},
        )
    else:
        raise ValueError(f"Unknown OCPP message type: {msg_type}")


def build_call(msg_id: str, action: str, payload: dict) -> str:
    """Build a CALL message JSON string."""
    return json.dumps([CALL, msg_id, action, payload])


def build_call_result(msg_id: str, payload: dict) -> str:
    """Build a CALL_RESULT message JSON string."""
    return json.dumps([CALL_RESULT, msg_id, payload])


def build_call_error(msg_id: str, error_code: str, description: str, details: dict = None) -> str:
    """Build a CALL_ERROR message JSON string."""
    return json.dumps([CALL_ERROR, msg_id, error_code, description, details or {}])
