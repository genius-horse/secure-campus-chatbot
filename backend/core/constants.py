from enum import Enum


ROLE_ORDER = {
    "public": 0,
    "student": 1,
    "teacher": 2,
    "admin": 3,
}


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"
    PRIVATE = "private"


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Action(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    PARTIALLY_ALLOWED = "partially_allowed"
