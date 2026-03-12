import pdfplumber
import re
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from .base_parser import BaseParser
from core.transaction import Transaction


class BEAParser(BaseParser):
    """Parser for Bank of East Asia (BEA) statements."""

    bank_name = "BEA"
    default_currency = "HKD"

    # Date format: "11DEC25"
    DATE_FORMATS = ["%d%b%y", "%d%b%Y", "%d-%b-%y", "%d-%b-%Y"]

    CURRENCY_MAP = {
        "HKD": "HKD",
        "USD": "USD",
        "EUR": "EUR",
        "CNY": "CNY",
        "AUD": "AUD",
        "GBP": "GBP",
        "JPY": "JPY",
    }

    def parse(self, pdf_path: str) -> List[Transaction]:
        transactions = []
        current_currency = self.default_currency

        with pdfplumber.open(pdf_path) as pdf:
            # Extract customer name from first page
            first_page_text = pdf.pages[0].extract_text() or ""
            self.customer_name = self.extract_customer_name(first_page_text)

            for page in pdf.pages:
                # First try table extraction
                tables = page.extract_tables()

                for table in tables:
                    if not table:
                        continue

                    for row in table:
                        # Check for currency indicator
                        row_text = " ".join(str(cell or "") for cell in row)
                        for curr in self.CURRENCY_MAP:
                            if curr in row_text and "Account" in row_text:
                                current_currency = curr
                                break

                        transaction = self._parse_row(row, current_currency)
                        if transaction:
                            transaction.customer_name = self.customer_name
                            transactions.append(transaction)

                # Also try text-based extraction for complex layouts
                text = page.extract_text() or ""
                text_transactions = self._parse_text(text, current_currency)
                for t in text_transactions:
                    t.customer_name = self.customer_name
                transactions.extend(text_transactions)

        # Remove duplicates based on date, amount, and description
        return self._deduplicate(transactions)

    def extract_customer_name(self, text: str) -> str:
        """Extract customer name from BEA statement."""
        # BEA format: Customer name appears after "Page 頁 數 X of Y" line
        # Example: "Page 頁 數 1 of 6\nA&B SOLUTIONS LIMITED"
        match = re.search(r"Page 頁 數 \d+ of \d+\s*\n([A-Z][A-Za-z0-9&\s\-\.]+(?:LIMITED|LTD|INC|CORP|LLC|COMPANY|CO\.|PTE)?)", text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Clean up - remove "PRIVATE AND CONFIDENTIAL" if it got captured
            name = re.sub(r"\s*PRIVATE AND CONFIDENTIAL.*", "", name, flags=re.IGNORECASE)
            return name.strip()

        # Alternative: look for company name pattern at start of document
        lines = text.split('\n')
        for i, line in enumerate(lines[:10]):
            # Look for lines that look like company names
            if re.match(r"^[A-Z][A-Z0-9&\s\-\.]+(?:LIMITED|LTD|INC|CORP)$", line.strip(), re.IGNORECASE):
                return line.strip()

        return ""

    def _parse_row(self, row: List, currency: str) -> Optional[Transaction]:
        """Parse a single row into a Transaction."""
        if not row or len(row) < 5:
            return None

        # Clean row data
        row = [str(cell).strip() if cell else "" for cell in row]

        try:
            # BEA columns: Cur, Date, Bk Ref, Transaction Details, Deposit, Withdrawal, Balance
            # Find the date column (usually contains format like "11DEC25")
            date_idx = -1
            for i, cell in enumerate(row):
                if self._is_date(cell):
                    date_idx = i
                    break

            if date_idx == -1:
                return None

            date_str = row[date_idx]
            date = self._parse_date(date_str)
            if not date:
                return None

            # Find description (usually after date and ref)
            description_parts = []
            for i in range(date_idx + 1, len(row)):
                cell = row[i]
                if cell and not self._is_amount(cell):
                    description_parts.append(cell)
                elif self._is_amount(cell):
                    break

            description = " ".join(description_parts)

            # Find deposit and withdrawal amounts (usually last columns before balance)
            amounts = []
            for cell in reversed(row):
                if self._is_amount(cell):
                    amounts.append(self.clean_amount(cell))
                if len(amounts) >= 3:  # Balance, Withdrawal, Deposit
                    break

            if len(amounts) < 2:
                return None

            # amounts are in reverse order: [balance, withdrawal, deposit]
            deposit = amounts[2] if len(amounts) > 2 else Decimal("0")
            withdrawal = amounts[1] if len(amounts) > 1 else Decimal("0")

            if deposit > 0:
                amount = deposit
                transaction_type = "in"
            elif withdrawal > 0:
                amount = withdrawal
                transaction_type = "out"
            else:
                return None

            # Check for currency in row
            row_currency = currency
            for cell in row[:3]:  # Currency usually in first columns
                cell_upper = cell.upper()
                if cell_upper in self.CURRENCY_MAP:
                    row_currency = cell_upper
                    break

            return Transaction(
                date=date,
                amount=amount,
                currency=row_currency,
                description=description,
                transaction_type=transaction_type,
                bank_name=self.bank_name,
            )

        except Exception:
            return None

    def _parse_text(self, text: str, default_currency: str) -> List[Transaction]:
        """Parse transactions from text when table extraction fails."""
        transactions = []

        # Pattern for BEA transaction lines
        # Example: "11DEC25 REF123 PAYMENT TO VENDOR 1,234.56"
        pattern = r"(\d{2}[A-Z]{3}\d{2})\s+(\S+)\s+(.+?)\s+([\d,]+\.\d{2})"

        for match in re.finditer(pattern, text):
            try:
                date_str = match.group(1)
                description = match.group(3).strip()
                amount_str = match.group(4)

                date = self._parse_date(date_str)
                if not date:
                    continue

                amount = self.clean_amount(amount_str)
                if amount <= 0:
                    continue

                # Determine transaction type from description keywords
                transaction_type = "out"
                credit_keywords = ["DEPOSIT", "CREDIT", "TRANSFER IN", "RECEIVED"]
                for keyword in credit_keywords:
                    if keyword in description.upper():
                        transaction_type = "in"
                        break

                transactions.append(
                    Transaction(
                        date=date,
                        amount=amount,
                        currency=default_currency,
                        description=description,
                        transaction_type=transaction_type,
                        bank_name=self.bank_name,
                    )
                )
            except Exception:
                continue

        return transactions

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse BEA date format."""
        if not date_str:
            return None

        date_str = date_str.strip().upper()

        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None

    def _is_date(self, text: str) -> bool:
        """Check if text looks like a BEA date."""
        if not text:
            return False
        # Pattern: 11DEC25 or 11-DEC-25
        return bool(re.match(r"^\d{2}[A-Z]{3}\d{2}$", text.upper()))

    def _is_amount(self, text: str) -> bool:
        """Check if text looks like an amount."""
        if not text:
            return False
        # Remove currency symbols and check for number pattern
        cleaned = re.sub(r"[,$\s]", "", text)
        return bool(re.match(r"^-?\d+\.?\d*$", cleaned))

    def _deduplicate(self, transactions: List[Transaction]) -> List[Transaction]:
        """Remove duplicate transactions."""
        seen = set()
        unique = []
        for t in transactions:
            key = (t.date.date(), t.amount, t.description[:50])
            if key not in seen:
                seen.add(key)
                unique.append(t)
        return unique
