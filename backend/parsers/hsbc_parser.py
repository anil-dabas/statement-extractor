import pdfplumber
import re
from typing import List, Optional, Tuple, Dict
from datetime import datetime
from decimal import Decimal

from .base_parser import BaseParser
from core.transaction import Transaction


class HSBCParser(BaseParser):
    """Parser for HSBC bank statements using column-position-based extraction."""

    bank_name = "HSBC"
    default_currency = "HKD"

    DATE_FORMATS = [
        "%d %b",
        "%d %b %Y",
        "%d %b %y",
        "%d-%b",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d/%m",
        "%d/%m/%Y",
    ]

    def __init__(self):
        super().__init__()
        self.statement_year: Optional[int] = None

    def parse(self, pdf_path: str) -> List[Transaction]:
        """Parse HSBC statement page by page for accurate multi-page extraction."""
        transactions = []

        with pdfplumber.open(pdf_path) as pdf:
            # First pass: extract year and customer name from plain text
            full_text_plain = ""
            for page in pdf.pages:
                full_text_plain += (page.extract_text() or "") + "\n"

            self.statement_year = self._extract_year(full_text_plain)
            self.customer_name = self.extract_customer_name(full_text_plain)

            # Second pass: process each page for transactions
            # Track column positions and current currency across pages
            current_currency = "HKD"
            column_positions = None  # (deposit_col, withdrawal_col, balance_col)

            for page in pdf.pages:
                page_text = page.extract_text(layout=True) or ""

                # Extract transactions from this page
                page_txns, column_positions, current_currency = self._parse_page(
                    page_text, column_positions, current_currency
                )
                transactions.extend(page_txns)

        # Set customer name for all transactions
        for t in transactions:
            t.customer_name = self.customer_name

        return transactions

    def _parse_page(
        self, page_text: str,
        prev_columns: Optional[Tuple[int, int, int]],
        prev_currency: str
    ) -> Tuple[List[Transaction], Optional[Tuple[int, int, int]], str]:
        """Parse a single page and return transactions, column positions, and current currency."""
        transactions = []
        lines = page_text.split('\n')

        current_columns = prev_columns
        current_currency = prev_currency

        current_date = None
        current_block = []

        i = 0
        while i < len(lines):
            line = lines[i]

            # Check for header line to update column positions
            if 'Deposit' in line and 'Withdrawal' in line and 'Balance' in line:
                deposit_col = line.find('Deposit')
                withdrawal_col = line.find('Withdrawal')
                balance_col = line.find('Balance')
                current_columns = (deposit_col, withdrawal_col, balance_col)
                # Discard any pending block from before the header (e.g., summary section)
                current_date = None
                current_block = []
                i += 1
                continue

            # Check for currency change (FCY section)
            ccy_match = re.match(r'^\s*(USD|EUR|GBP|CNY|AUD|JPY|CAD|CHF)\s+(\d{1,2}\s+[A-Za-z]{3})\s', line)
            if ccy_match:
                # Process previous block if exists
                if current_date and current_block and current_columns:
                    txns = self._extract_transactions_from_block(
                        current_date, current_block, current_columns, current_currency
                    )
                    transactions.extend(txns)

                current_currency = ccy_match.group(1)
                current_date = ccy_match.group(2)
                current_block = [line]
                i += 1
                continue

            # Check for section headers (skip them)
            if 'HSBC Business Direct' in line and 'Savings' in line:
                # Check if this is HKD or FCY section
                if 'HKD Savings' in line:
                    current_currency = "HKD"
                i += 1
                continue

            # Skip portfolio summary sections
            if 'PortfolioSummary' in line.replace(' ', '') or 'Portfolio Summary' in line:
                # Process any pending block before summary section
                if current_date and current_block and current_columns:
                    txns = self._extract_transactions_from_block(
                        current_date, current_block, current_columns, current_currency
                    )
                    transactions.extend(txns)
                    current_date = None
                    current_block = []
                i += 1
                continue

            # Skip account summary lines
            if 'AccountNumber' in line.replace(' ', '') and 'CCY' in line:
                i += 1
                continue
            if 'Deposits' in line and ('HKDSavings' in line.replace(' ', '') or 'HKDCurrent' in line.replace(' ', '') or 'ForeignCurrency' in line.replace(' ', '')):
                i += 1
                continue

            # Skip summary/total lines
            if 'TotalNo.' in line or 'TotalDeposit' in line or 'TotalWithdrawal' in line:
                # Process any pending block before summary
                if current_date and current_block and current_columns:
                    txns = self._extract_transactions_from_block(
                        current_date, current_block, current_columns, current_currency
                    )
                    transactions.extend(txns)
                    current_date = None
                    current_block = []
                i += 1
                continue

            # Skip exchange rate lines (e.g., "GBP 9.877244 USD 7.823250 EUR 8.470233")
            if 'ExchangeRate' in line.replace(' ', ''):
                i += 1
                continue
            # Skip lines that are currency exchange rate data (currency followed by rate with 4+ decimals)
            if re.match(r'^\s*(USD|EUR|GBP|CNY|AUD|JPY|CAD|CHF)\s+\d+\.\d{4,}', line):
                i += 1
                continue
            # Skip lines that look like exchange rate listings
            exchange_rate_pattern = re.findall(r'(USD|EUR|GBP|CNY|AUD|JPY|CAD|CHF)\s+\d+\.\d{4,}', line)
            if len(exchange_rate_pattern) >= 2:
                i += 1
                continue

            # Skip other non-transaction lines
            if not line.strip():
                i += 1
                continue

            # Check for date pattern at start of line
            date_match = re.match(r'^\s*(\d{1,2}\s+[A-Za-z]{3})\s', line)

            if date_match:
                # Process previous block
                if current_date and current_block and current_columns:
                    txns = self._extract_transactions_from_block(
                        current_date, current_block, current_columns, current_currency
                    )
                    transactions.extend(txns)

                # Start new block
                current_date = date_match.group(1)
                current_block = [line]
            else:
                # Continuation line - add to current block
                if current_date:
                    current_block.append(line)

            i += 1

        # Process last block on page
        if current_date and current_block and current_columns:
            txns = self._extract_transactions_from_block(
                current_date, current_block, current_columns, current_currency
            )
            transactions.extend(txns)

        return transactions, current_columns, current_currency

    def _extract_transactions_from_block(
        self, date_str: str, block_lines: List[str],
        columns: Tuple[int, int, int], currency: str
    ) -> List[Transaction]:
        """Extract transactions from a block of lines using column positions."""
        transactions = []
        deposit_col, withdrawal_col, balance_col = columns

        # Skip B/F and C/F balance lines
        full_block = '\n'.join(block_lines)
        if 'B/F BALANCE' in full_block.upper() or 'C/F BALANCE' in full_block.upper():
            return transactions

        # Skip portfolio summary blocks
        if 'PortfolioSummary' in full_block.replace(' ', '') or 'Portfolio Summary' in full_block:
            return transactions
        if 'AccountNumber' in full_block.replace(' ', '') and 'Deposits' in full_block:
            return transactions

        # Parse date
        date = self._parse_date(date_str)
        if not date:
            return transactions

        # Calculate column boundaries using midpoints
        deposit_start = deposit_col - 5
        deposit_end = deposit_col + (withdrawal_col - deposit_col) // 2 + 3
        withdrawal_start = deposit_end
        withdrawal_end = withdrawal_col + (balance_col - withdrawal_col) // 2 + 3
        balance_start = withdrawal_end

        # Collect amounts and descriptions
        deposit_amounts = []
        withdrawal_amounts = []
        description_parts = []

        for line in block_lines:
            # Skip exchange rate lines
            if 'ExchangeRate' in line.replace(' ', ''):
                continue
            if re.match(r'^\s*(USD|EUR|GBP|CNY|AUD|JPY|CAD|CHF)\s+\d+\.\d{4,}', line):
                continue
            exchange_rate_count = len(re.findall(r'(USD|EUR|GBP|CNY|AUD|JPY|CAD|CHF)\s+\d+\.\d{4,}', line))
            if exchange_rate_count >= 2:
                continue

            # Find all amounts in this line (only 2 decimal places, not exchange rates)
            for match in re.finditer(r'([\d,]+\.\d{2})(?!\d)', line):
                amount_str = match.group(1)
                position = match.start()

                try:
                    amount = Decimal(amount_str.replace(',', ''))
                    if amount <= 0:
                        continue
                except:
                    continue

                # Determine column based on position
                if position >= balance_start:
                    # Balance column - skip
                    continue
                elif position >= withdrawal_start:
                    withdrawal_amounts.append(amount)
                elif position >= deposit_start:
                    deposit_amounts.append(amount)

            # Extract description
            desc_end = min(deposit_col - 5, len(line)) if deposit_col > 0 else len(line)
            desc_part = line[:desc_end].strip()
            # Remove date pattern
            desc_part = re.sub(r'^\d{1,2}\s+[A-Za-z]{3}\s*', '', desc_part)
            # Remove currency code
            desc_part = re.sub(r'^(USD|EUR|GBP|CNY|AUD|JPY|CAD|CHF)\s+\d{1,2}\s+[A-Za-z]{3}\s*', '', desc_part)
            if desc_part:
                description_parts.append(desc_part)

        # Combine description
        description = ' '.join(description_parts).strip()
        description = re.sub(r'\s+', ' ', description)

        # Create transactions
        for amount in deposit_amounts:
            transactions.append(Transaction(
                date=date,
                amount=amount,
                currency=currency,
                description=description,
                transaction_type="in",
                bank_name=self.bank_name,
            ))

        for amount in withdrawal_amounts:
            transactions.append(Transaction(
                date=date,
                amount=amount,
                currency=currency,
                description=description,
                transaction_type="out",
                bank_name=self.bank_name,
            ))

        return transactions

    def extract_customer_name(self, text: str) -> str:
        """Extract customer name from HSBC statement."""
        # Pattern 1: "Statement\nCOMPANY NAME Number"
        match = re.search(
            r"Statement\s*\n([A-Z][A-Za-z0-9&\s\-\.,]+(?:LIMITED|LTD|INC|CORP|LLC|COMPANY|CO\.,?\s*LIMITED))\s*Number",
            text, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        # Pattern 2: Company name line followed by "Number :"
        match = re.search(
            r"^([A-Z][A-Z0-9&\s\-\.,]+(?:LIMITED|LTD|CO\.,?\s*LIMITED))\s+Number\s*:",
            text, re.MULTILINE | re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        # Pattern 3: Look in first 15 lines
        lines = text.split('\n')
        for line in lines[:15]:
            line = line.strip()
            if re.match(r"^[A-Z][A-Z0-9&\s\-\.,]+(?:LIMITED|LTD|INC|CORP|GLOBAL|CO\.,?\s*LIMITED)$", line, re.IGNORECASE):
                if len(line) > 5 and "HSBC" not in line.upper() and "STATEMENT" not in line.upper():
                    return line

        return ""

    def _extract_year(self, text: str) -> Optional[int]:
        """Extract statement year from text."""
        match = re.search(r"\d{1,2}\s+[A-Za-z]+\s+(20\d{2})", text)
        if match:
            return int(match.group(1))

        match = re.search(r"(20\d{2})", text)
        if match:
            return int(match.group(1))

        return datetime.now().year

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse HSBC date format."""
        if not date_str:
            return None

        date_str = date_str.strip()
        year = self.statement_year or datetime.now().year

        for fmt in self.DATE_FORMATS:
            try:
                if "%Y" not in fmt and "%y" not in fmt:
                    # Add year to the date string before parsing to handle leap years
                    parsed = datetime.strptime(f"{date_str} {year}", f"{fmt} %Y")
                else:
                    parsed = datetime.strptime(date_str, fmt)
                return parsed
            except ValueError:
                continue

        return None
