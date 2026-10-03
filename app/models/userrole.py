from enum import Enum as PyEnum

class UserRole(str, PyEnum):
    client = "client"
    photographer = "photographer"
    studio = "studio"