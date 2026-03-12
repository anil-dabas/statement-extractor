import pdfplumber
import re
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from .base_parser import BaseParser
from core.transaction import Transaction


class AirwallexParser(BaseParser):
    """Parser for Airwallex bank statements."""

    bank_name = "Airwallex"
    default_currency = "USD"

    # Date format: "Dec 02 2025"
    DATE_FORMATS = ["%b %d %Y", "%B %d %Y", "%b %d, %Y"]

    def parse(self, pdf_path: str) -> List[Transaction]:
        transactions = []

        with pdfplumber.open(pdf_path) as pdf:
            # Extract customer name from first page
            first_page_text = pdf.pages[0].extract_text() or ""
            self.customer_name = self.extract_customer_name(first_page_text)

            for page in pdf.pages:
                tables = page.extract_tables()

                for table in tables:
                    if not table:
                        continue

                    # Find the header row
                    header_idx = self._find_header_row(table)
                    if header_idx == -1:
                        continue

                    # Parse transactions from table
                    for row in table[header_idx + 1 :]:
                        transaction = self._parse_row(row)
                        if transaction:
                            transaction.customer_name = self.customer_name
                            transactions.append(transaction)

        return transactions

    def extract_customer_name(self, text: str) -> str:
        """Extract customer name from Airwallex statement."""
        # Pattern: "Account Holder" followed by name on next line
        # Example: "Account Holder Account Details\nA&B Solutions Limited Account number:"
        match = re.search(r"Account Holder.*?\n([A-Z][A-Za-z0-9&\s\-\.]+(?:Limited|Ltd|Inc|Corp|LLC|Company|Co\.|PTE))", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Alternative: look for name before "Account number"
        match = re.search(r"\n([A-Z][A-Za-z0-9&\s\-\.]+(?:Limited|Ltd|Inc|Corp|LLC|Company|Co\.|PTE))\s*Account number", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return ""

    def _find_header_row(self, table: List[List]) -> int:
        """Find the row index containing the header."""
        for i, row in enumerate(table):
            row_text = " ".join(str(cell or "") for cell in row).lower()
            if "date" in row_text and ("credit" in row_text or "debit" in row_text):
                return i
        return -1

    def _parse_row(self, row: List) -> Optional[Transaction]:
        """Parse a single row into a Transaction."""
        if not row or len(row) < 4:
            return None

        # Clean row data
        row = [str(cell).strip() if cell else "" for cell in row]

        # Skip empty rows or header-like rows
        if not row[0] or "date" in row[0].lower():
            return None

        try:
            # Column order: Date, Details, Credit, Debit, Balance
            date_str = row[0]
            description = row[1] if len(row) > 1 else ""
            credit = row[2] if len(row) > 2 else ""
            debit = row[3] if len(row) > 3 else ""

            # Parse date
            date = self._parse_date(date_str)
            if not date:
                return None

            # Determine transaction type and amount
            credit_amount = self.clean_amount(credit)
            debit_amount = self.clean_amount(debit)

            if credit_amount > 0:
                amount = credit_amount
                transaction_type = "in"
            elif debit_amount > 0:
                amount = debit_amount
                transaction_type = "out"
            else:
                return None

            return Transaction(
                date=date,
                amount=amount,
                currency=self.default_currency,
                description=description,
                transaction_type=transaction_type,
                bank_name=self.bank_name,
            )

        except Exception:
            return None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse Airwallex date format."""
        if not date_str:
            return None

        # Clean the date string
        date_str = re.sub(r"\s+", " ", date_str.strip())

        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None
