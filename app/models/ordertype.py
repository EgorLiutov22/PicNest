from enum import Enum as PyEnum


class OrderType(str, PyEnum):
    photographer_only = "photographer_only"
    studio_only = "studio_only"
    combined = "combined"