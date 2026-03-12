from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class Transaction:
    """Represents a single bank transaction."""

    date: datetime
    amount: Decimal
    currency: str
    description: str
    transaction_type: str  # 'in' or 'out'
    bank_name: str
    exchange_rate: Optional[str] = None
    nature: str = ""  # Empty for manual fill by user
    remark: str = ""
    customer_name: str = ""

    def to_dict(self) -> dict:
        """Convert transaction to dictionary for JSON serialization."""
        return {
            "date": self.date.isoformat(),
            "amount": str(self.amount),
            "currency": self.currency,
            "description": self.description,
            "transaction_type": self.transaction_type,
            "bank_name": self.bank_name,
            "exchange_rate": self.exchange_rate or "",
            "nature": self.nature,
            "remark": self.remark,
            "customer_name": self.customer_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Transaction":
        """Create a Transaction from a dictionary."""
        return cls(
            date=datetime.fromisoformat(data["date"]),
            amount=Decimal(data["amount"]),
            currency=data["currency"],
            description=data["description"],
            transaction_type=data["transaction_type"],
            bank_name=data["bank_name"],
            exchange_rate=data.get("exchange_rate") or None,
            nature=data.get("nature", ""),
            remark=data.get("remark", ""),
            customer_name=data.get("customer_name", ""),
        )
