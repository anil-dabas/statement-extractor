import pdfplumber
import re
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from .base_parser import BaseParser
from core.transaction import Transaction


class HangSengParser(BaseParser):
    """Parser for Hang Seng Bank statements."""

    bank_name = "Hang Seng"
    default_currency = "HKD"

    # Date format: "29 Nov", "16 Dec" (needs year inference)
    DATE_FORMATS = [
        "%d %b",
        "%d %b %Y",
        "%d %b %y",
        "%d-%b",
        "%d-%b-%Y",
        "%d-%b-%y",
    ]

    def __init__(self):
        super().__init__()
        self.statement_year: Optional[int] = None

    def parse(self, pdf_path: str) -> List[Transaction]:
        transactions = []

        with pdfplumber.open(pdf_path) as pdf:
            # Try to extract statement year and customer name from first page
            first_page_text = pdf.pages[0].extract_text() or ""
            self.statement_year = self._extract_year(first_page_text)
            self.customer_name = self.extract_customer_name(first_page_text)

            for page in pdf.pages:
                tables = page.extract_tables()

                for table in tables:
                    if not table:
                        continue

                    # Check if this is a transaction table
                    header_row = table[0] if table else []
                    header_text = " ".join(str(cell or "") for cell in header_row).lower()

                    # Table with CCY column (Foreign Currency table)
                    if "ccy" in header_text and "date" in header_text:
                        parsed = self._parse_foreign_currency_table(table)
                        for t in parsed:
                            t.customer_name = self.customer_name
                        transactions.extend(parsed)
                    # HKD table (no CCY column)
                    elif "date" in header_text and ("deposit" in header_text or "withdrawal" in header_text):
                        parsed = self._parse_hkd_table(table)
                        for t in parsed:
                            t.customer_name = self.customer_name
                        transactions.extend(parsed)

        return transactions

    def _parse_hkd_table(self, table: List[List]) -> List[Transaction]:
        """Parse HKD transaction table."""
        transactions = []

        # Find column indices from header
        header_row = table[0] if table else []
        header_text = [str(cell or "").lower().strip() for cell in header_row]

        date_idx = -1
        desc_idx = -1
        deposit_idx = -1
        withdrawal_idx = -1

        for i, h in enumerate(header_text):
            if "date" in h:
                date_idx = i
            elif "transaction" in h or "details" in h:
                desc_idx = i
            elif "deposit" in h:
                deposit_idx = i
            elif "withdrawal" in h:
                withdrawal_idx = i

        if date_idx == -1:
            return transactions

        # Process data rows
        for row in table[1:]:
            if not row or len(row) <= date_idx:
                continue

            row_text = " ".join(str(cell or "") for cell in row)
            if not row_text.strip():
                continue

            # Get merged cell data
            dates_cell = str(row[date_idx] or "") if date_idx < len(row) else ""
            desc_cell = str(row[desc_idx] or "") if desc_idx >= 0 and desc_idx < len(row) else ""
            deposit_cell = str(row[deposit_idx] or "") if deposit_idx >= 0 and deposit_idx < len(row) else ""
            withdrawal_cell = str(row[withdrawal_idx] or "") if withdrawal_idx >= 0 and withdrawal_idx < len(row) else ""

            # Split merged cells
            dates = [d.strip() for d in dates_cell.split('\n') if d.strip()]
            descriptions = [d.strip() for d in desc_cell.split('\n') if d.strip()]
            deposits = [d.strip() for d in deposit_cell.split('\n') if d.strip()]
            withdrawals = [d.strip() for d in withdrawal_cell.split('\n') if d.strip()]

            # Match transactions - HKD currency
            parsed = self._match_hkd_transactions(dates, descriptions, deposits, withdrawals)
            transactions.extend(parsed)

        return transactions

    def _parse_foreign_currency_table(self, table: List[List]) -> List[Transaction]:
        """Parse Foreign Currency transaction table with CCY column."""
        transactions = []

        # Find column indices from header
        header_row = table[0] if table else []
        header_text = [str(cell or "").lower().strip() for cell in header_row]

        ccy_idx = -1
        date_idx = -1
        desc_idx = -1
        deposit_idx = -1
        withdrawal_idx = -1

        for i, h in enumerate(header_text):
            if "ccy" in h:
                ccy_idx = i
            elif "date" in h:
                date_idx = i
            elif "transaction" in h or "details" in h:
                desc_idx = i
            elif "deposit" in h:
                deposit_idx = i
            elif "withdrawal" in h:
                withdrawal_idx = i

        if date_idx == -1 or ccy_idx == -1:
            return transactions

        # Process data rows
        for row in table[1:]:
            if not row or len(row) <= max(ccy_idx, date_idx):
                continue

            row_text = " ".join(str(cell or "") for cell in row)
            if not row_text.strip():
                continue

            # Get merged cell data
            ccy_cell = str(row[ccy_idx] or "") if ccy_idx < len(row) else ""
            dates_cell = str(row[date_idx] or "") if date_idx < len(row) else ""
            desc_cell = str(row[desc_idx] or "") if desc_idx >= 0 and desc_idx < len(row) else ""
            deposit_cell = str(row[deposit_idx] or "") if deposit_idx >= 0 and deposit_idx < len(row) else ""
            withdrawal_cell = str(row[withdrawal_idx] or "") if withdrawal_idx >= 0 and withdrawal_idx < len(row) else ""

            # Split merged cells
            currencies = [c.strip() for c in ccy_cell.split('\n') if c.strip()]
            dates = [d.strip() for d in dates_cell.split('\n') if d.strip()]
            descriptions = [d.strip() for d in desc_cell.split('\n') if d.strip()]
            deposits = [d.strip() for d in deposit_cell.split('\n') if d.strip()]
            withdrawals = [d.strip() for d in withdrawal_cell.split('\n') if d.strip()]

            # Match transactions with currencies
            parsed = self._match_foreign_currency_transactions(currencies, dates, descriptions, deposits, withdrawals)
            transactions.extend(parsed)

        return transactions

    def _match_hkd_transactions(
        self,
        dates: List[str],
        descriptions: List[str],
        deposits: List[str],
        withdrawals: List[str]
    ) -> List[Transaction]:
        """Match HKD transactions."""
        transactions = []

        # Filter valid data
        valid_dates = [d for d in dates if self._is_valid_date(d)]
        valid_descriptions = [d for d in descriptions if not any(
            skip in d.upper() for skip in ["B/F BALANCE", "C/F BALANCE", "TRANSACTION SUMMARY"]
        )]
        valid_deposits = [d for d in deposits if self._is_amount(d)]
        valid_withdrawals = [d for d in withdrawals if self._is_amount(d)]

        # Create transactions for deposits
        deposit_date_idx = 0
        for deposit in valid_deposits:
            amount = self.clean_amount(deposit)
            if amount <= 0:
                continue

            # Find matching date and description
            date = None
            description = ""

            # Look through descriptions to find credit-related ones
            for i, desc in enumerate(valid_descriptions):
                if self._is_credit_description(desc):
                    if deposit_date_idx < len(valid_dates):
                        date = self._parse_date(valid_dates[deposit_date_idx])
                    description = desc
                    deposit_date_idx += 1
                    break

            if not date and valid_dates:
                date = self._parse_date(valid_dates[0])

            if date:
                transactions.append(Transaction(
                    date=date,
                    amount=amount,
                    currency="HKD",
                    description=description or "Deposit",
                    transaction_type="in",
                    bank_name=self.bank_name,
                ))

        # Create transactions for withdrawals
        for withdrawal in valid_withdrawals:
            amount = self.clean_amount(withdrawal)
            if amount <= 0:
                continue

            date = None
            description = ""

            # Find non-credit description
            for desc in valid_descriptions:
                if not self._is_credit_description(desc):
                    description = desc
                    break

            if valid_dates:
                # Use a later date for withdrawals
                idx = min(len(valid_deposits), len(valid_dates) - 1)
                date = self._parse_date(valid_dates[idx])

            if date:
                transactions.append(Transaction(
                    date=date,
                    amount=amount,
                    currency="HKD",
                    description=description or "Withdrawal",
                    transaction_type="out",
                    bank_name=self.bank_name,
                ))

        return transactions

    def _match_foreign_currency_transactions(
        self,
        currencies: List[str],
        dates: List[str],
        descriptions: List[str],
        deposits: List[str],
        withdrawals: List[str]
    ) -> List[Transaction]:
        """Match foreign currency transactions with their correct currencies."""
        transactions = []

        # Parse the structure: currencies repeat for each currency's transactions
        # Example: USD appears 3 times (B/F, CREDIT INTEREST, C/F), then EUR 3 times, etc.

        valid_currencies = [c.upper() for c in currencies if c.upper() in ["USD", "EUR", "CNY", "AUD", "GBP", "JPY", "HKD"]]
        valid_dates = [d for d in dates if self._is_valid_date(d)]
        valid_descriptions = [d for d in descriptions if not any(
            skip in d.upper() for skip in ["B/F BALANCE", "C/F BALANCE"]
        )]
        valid_deposits = [d for d in deposits if self._is_amount(d)]

        # Count how many times each currency appears to understand the pattern
        # In the sample: USD appears for transactions at indices 0,1,2 (B/F, CREDIT INT, C/F)
        #                EUR appears for transactions at indices 3,4,5
        #                CNY appears for transactions at indices 6,7,8

        if not valid_currencies:
            return transactions

        # Each currency has 3 entries: B/F BALANCE, transaction(s), C/F BALANCE
        # We need to match each deposit with its currency

        # Find unique currencies in order
        seen_currencies = []
        for c in valid_currencies:
            if c not in seen_currencies:
                seen_currencies.append(c)

        # Match deposits with currencies based on their position
        # Deposits appear in order: first for USD, then EUR, then CNY
        for i, deposit in enumerate(valid_deposits):
            amount = self.clean_amount(deposit)
            if amount <= 0:
                continue

            # Determine which currency this deposit belongs to
            currency_idx = i % len(seen_currencies) if seen_currencies else 0
            currency = seen_currencies[currency_idx] if currency_idx < len(seen_currencies) else "USD"

            # Find corresponding date
            # Each currency section has ~3 dates, deposit is usually the 2nd one
            # So for currency i, the transaction date would be around index (i * 3 + 1)
            date = None
            desc = "CREDIT INTEREST"

            # Try to find the actual transaction date for this currency
            # Look for dates that match this currency's section
            currency_section_start = currency_idx * 3
            if currency_section_start + 1 < len(valid_dates):
                date = self._parse_date(valid_dates[currency_section_start + 1])
            elif valid_dates:
                date = self._parse_date(valid_dates[min(i, len(valid_dates) - 1)])

            if not date:
                date = datetime.now()

            transactions.append(Transaction(
                date=date,
                amount=amount,
                currency=currency,
                description=desc,
                transaction_type="in",
                bank_name=self.bank_name,
            ))

        return transactions

    def extract_customer_name(self, text: str) -> str:
        """Extract customer name from Hang Seng statement."""
        match = re.search(r"Account Number[^\n]+\n([A-Z][A-Za-z0-9&\s\-\.]+(?:LIMITED|LTD|INC|CORP|LLC|COMPANY)?)\s+Statement", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        lines = text.split('\n')
        for line in lines[:10]:
            line = line.strip()
            if re.match(r"^[A-Z][A-Z0-9&\s\-\.]+(?:LIMITED|LTD|INC|CORP)$", line, re.IGNORECASE):
                return line

        return ""

    def _extract_year(self, text: str) -> Optional[int]:
        """Extract statement year from text."""
        match = re.search(r"Statement Date[^\d]*(\d{1,2}\s+\w+\s+)?(\d{4})", text)
        if match:
            return int(match.group(2))

        year_match = re.search(r"20\d{2}", text)
        if year_match:
            return int(year_match.group())
        return datetime.now().year

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse Hang Seng date format."""
        if not date_str:
            return None

        date_str = date_str.strip()

        if not self._is_valid_date(date_str):
            return None

        for fmt in self.DATE_FORMATS:
            try:
                parsed = datetime.strptime(date_str, fmt)
                if "%Y" not in fmt and "%y" not in fmt:
                    year = self.statement_year or datetime.now().year
                    parsed = parsed.replace(year=year)
                return parsed
            except ValueError:
                continue

        return None

    def _is_valid_date(self, text: str) -> bool:
        """Check if text looks like a valid date."""
        if not text:
            return False
        return bool(re.match(r"^\d{1,2}\s+[A-Za-z]{3}$", text.strip()))

    def _is_amount(self, text: str) -> bool:
        """Check if text looks like an amount."""
        if not text:
            return False
        cleaned = re.sub(r"[,$\s]", "", text)
        return bool(re.match(r"^-?[\d,]+\.?\d*$", cleaned))

    def _is_credit_description(self, description: str) -> bool:
        """Determine if description indicates a credit/deposit."""
        credit_keywords = [
            "DEPOSIT", "CREDIT", "CREDIT INTEREST", "TRANSFER IN",
            "RECEIVED", "INWARD", "INTEREST", "REFUND", "TT CREDIT",
        ]
        description_upper = description.upper()
        return any(keyword in description_upper for keyword in credit_keywords)
