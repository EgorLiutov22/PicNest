from enum import Enum as PyEnum

class OrderStatus(str, PyEnum):
    pending_payment = "pending_payment"
    confirmed = "confirmed"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    disputed = "disputed"