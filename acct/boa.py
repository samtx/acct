import datetime
from dataclasses import dataclass


@dataclass
class BOATransaction:
    date: datetime.date
    description: str
    amount: float


