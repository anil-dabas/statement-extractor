import pdfplumber
import re
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from .base_parser import BaseParser
from core.transaction import Transaction


class DBSParser(BaseParser):
    """Parser for DBS Bank statements."""

    bank_name = "DBS"
    default_currency = "HKD"

    # Date format: "10-May-22"
    DATE_FORMATS = [
        "%d-%b-%y",
        "%d-%b-%Y",
        "%d %b %y",
        "%d %b %Y",
        "%d/%m/%y",
        "%d/%m/%Y",
    ]

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

                    # Find header row
                    header_idx = self._find_header_row(table)
                    if header_idx == -1:
                        # Try parsing without header
                        for row in table:
                            transaction = self._parse_row(row)
                            if transaction:
                                transaction.customer_name = self.customer_name
                                transactions.append(transaction)
                    else:
                        for row in table[header_idx + 1 :]:
                            transaction = self._parse_row(row)
                            if transaction:
                                transaction.customer_name = self.customer_name
                                transactions.append(transaction)

        return transactions

    def extract_customer_name(self, text: str) -> str:
        """Extract customer name from DBS statement."""
        # DBS format: Customer name appears after header, before address
        # Example: "EVERSTRETCH LIMITED\nFLAT A11 11/F..."
        lines = text.split('\n')
        for i, line in enumerate(lines[:15]):
            line = line.strip()
            # Look for company name pattern (all caps, ends with LIMITED/LTD/etc)
            if re.match(r"^[A-Z][A-Z0-9&\s\-\.]+(?:LIMITED|LTD|INC|CORP|LLC|COMPANY)$", line, re.IGNORECASE):
                # Make sure next line looks like an address
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip().upper()
                    if any(word in next_line for word in ["FLAT", "FLOOR", "ROOM", "UNIT", "BUILDING", "STREET", "ROAD"]):
                        return line
        return ""

    def _find_header_row(self, table: List[List]) -> int:
        """Find the row index containing the header."""
        for i, row in enumerate(table):
            row_text = " ".join(str(cell or "") for cell in row).lower()
            if "transaction date" in row_text or (
                "date" in row_text and "withdrawal" in row_text
            ):
                return i
        return -1

    def _parse_row(self, row: List) -> Optional[Transaction]:
        """Parse a single row into a Transaction."""
        if not row or len(row) < 4:
            return None

        # Clean row data
        row = [str(cell).strip() if cell else "" for cell in row]

        # Skip empty or header rows
        if not row[0] or "date" in row[0].lower():
            return None

        try:
            # DBS columns: Transaction Date, Value Date, Transaction Details, Withdrawal, Deposit, Balance
            # Or: Date, Details, Withdrawal, Deposit, Balance

            # Find the date
            date = None
            date_idx = -1
            for i, cell in enumerate(row[:2]):  # Date usually in first 2 columns
                parsed = self._parse_date(cell)
                if parsed:
                    date = parsed
                    date_idx = i
                    break

            if not date:
                return None

            # Find description (between date and amounts)
            description_parts = []
            amount_start_idx = len(row)

            for i in range(date_idx + 1, len(row)):
                cell = row[i]
                # Check if this looks like a date (value date) - skip it
                if self._parse_date(cell):
                    continue
                # Check if this is an amount
                if self._is_amount(cell):
                    amount_start_idx = i
                    break
                if cell:
                    description_parts.append(cell)

            description = " ".join(description_parts)

            # Parse amounts from remaining columns
            withdrawal = Decimal("0")
            deposit = Decimal("0")

            amount_cells = row[amount_start_idx:]
            if len(amount_cells) >= 2:
                # Withdrawal, Deposit, Balance order
                withdrawal = self.clean_amount(amount_cells[0])
                deposit = self.clean_amount(amount_cells[1])
            elif len(amount_cells) == 1:
                # Single amount - need to determine type from description
                amount = self.clean_amount(amount_cells[0])
                if self._is_credit_description(description):
                    deposit = amount
                else:
                    withdrawal = amount

            if deposit > 0:
                amount = deposit
                transaction_type = "in"
            elif withdrawal > 0:
                amount = withdrawal
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
        """Parse DBS date format."""
        if not date_str:
            return None

        date_str = date_str.strip()

        # Skip if it looks like an amount
        if self._is_amount(date_str):
            return None

        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None

    def _is_amount(self, text: str) -> bool:
        """Check if text looks like an amount."""
        if not text:
            return False
        cleaned = re.sub(r"[,$\s]", "", text)
        return bool(re.match(r"^-?[\d,]+\.?\d*$", cleaned)) and "." in text

    def _is_credit_description(self, description: str) -> bool:
        """Determine if description indicates a credit/deposit."""
        credit_keywords = [
            "DEPOSIT",
            "CREDIT",
            "TRANSFER IN",
            "RECEIVED",
            "INWARD",
            "INTEREST",
            "REFUND",
        ]
        description_upper = description.upper()
        return any(keyword in description_upper for keyword in credit_keywords)
