from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from decimal import Decimal, InvalidOperation
import re
from datetime import datetime

from core.transaction import Transaction


class BaseParser(ABC):
    """Abstract base class for bank statement parsers."""

    bank_name: str = "Unknown"
    default_currency: str = "HKD"

    def __init__(self):
        self.customer_name: str = ""

    @abstractmethod
    def parse(self, pdf_path: str) -> List[Transaction]:
        """
        Parse a bank statement PDF and extract transactions.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            List of Transaction objects
        """
        pass

    def clean_amount(self, amount_str: str) -> Decimal:
        """
        Clean and parse an amount string to Decimal.

        Handles formats like:
        - "1,234.56"
        - "1234.56"
        - "-1,234.56"
        - "(1,234.56)" for negative
        - "1,234.56 CR" for credit
        - "1,234.56 DR" for debit
        """
        if not amount_str or amount_str.strip() in ("", "-", "—", "N/A"):
            return Decimal("0")

        amount_str = str(amount_str).strip()

        # Check for parentheses (negative)
        is_negative = False
        if amount_str.startswith("(") and amount_str.endswith(")"):
            is_negative = True
            amount_str = amount_str[1:-1]

        # Check for CR/DR suffix
        if "CR" in amount_str.upper():
            amount_str = re.sub(r"\s*CR\s*", "", amount_str, flags=re.IGNORECASE)
        if "DR" in amount_str.upper():
            amount_str = re.sub(r"\s*DR\s*", "", amount_str, flags=re.IGNORECASE)
            is_negative = True

        # Check for leading minus
        if amount_str.startswith("-"):
            is_negative = True
            amount_str = amount_str[1:]

        # Remove currency symbols and commas
        amount_str = re.sub(r"[,$€£¥HKD\sUSD]", "", amount_str)

        try:
            amount = Decimal(amount_str)
            if is_negative:
                amount = -amount
            return amount
        except InvalidOperation:
            return Decimal("0")

    def parse_date(self, date_str: str, formats: List[str]) -> datetime:
        """
        Parse a date string using multiple possible formats.

        Args:
            date_str: The date string to parse
            formats: List of datetime format strings to try

        Returns:
            datetime object

        Raises:
            ValueError: If no format matches
        """
        date_str = date_str.strip()

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        raise ValueError(f"Could not parse date: {date_str}")

    def infer_year(self, month: int, reference_date: datetime = None) -> int:
        """
        Infer the year for a transaction when only month/day is provided.

        Uses the reference date (usually from the statement period) or current date.
        """
        if reference_date:
            return reference_date.year

        now = datetime.now()
        # If the month is in the future, assume it's from last year
        if month > now.month:
            return now.year - 1
        return now.year

    def extract_currency(self, text: str) -> str:
        """Extract currency code from text."""
        currency_patterns = {
            "USD": r"\bUSD\b|\bUS\$|\$(?!HK)",
            "HKD": r"\bHKD\b|\bHK\$",
            "EUR": r"\bEUR\b|€",
            "GBP": r"\bGBP\b|£",
            "CNY": r"\bCNY\b|\bRMB\b|¥",
            "AUD": r"\bAUD\b|\bA\$",
            "JPY": r"\bJPY\b",
        }

        for currency, pattern in currency_patterns.items():
            if re.search(pattern, text):
                return currency

        return self.default_currency

    def extract_customer_name(self, text: str) -> str:
        """
        Extract customer name from statement text.
        Override in subclasses for bank-specific patterns.
        """
        return ""

    def get_customer_name(self) -> str:
        """Return the extracted customer name."""
        return self.customer_name
