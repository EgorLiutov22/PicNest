from enum import Enum as PyEnum

class UserStatus(str, PyEnum):
    active = "active"
    pending_verification = "pending_verification"
    blocked = "blocked"