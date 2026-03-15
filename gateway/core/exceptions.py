# OCPP error codes as constants
NOT_IMPLEMENTED = "NotImplemented"
NOT_SUPPORTED = "NotSupported"
INTERNAL_ERROR = "InternalError"
PROTOCOL_ERROR = "ProtocolError"
SECURITY_ERROR = "SecurityError"
FORMATION_VIOLATION = "FormationViolation"
PROPERTY_CONSTRAINT_VIOLATION = "PropertyConstraintViolation"
OCCURRENCE_CONSTRAINT_VIOLATION = "OccurrenceConstraintViolation"
TYPE_CONSTRAINT_VIOLATION = "TypeConstraintViolation"
GENERIC_ERROR = "GenericError"


class OcppError(Exception):
    """Base OCPP error with error code."""
    def __init__(self, error_code: str, description: str = "", details: dict = None):
        self.error_code = error_code
        self.description = description
        self.details = details or {}
        super().__init__(description)
