import pdfplumber
from typing import Optional, Tuple
import re


class BankDetector:
    """Detects the bank type from a PDF statement."""

    BANK_PATTERNS = {
        "airwallex": [
            r"airwallex\.com",
            r"Airwallex",
            r"AIRWALLEX",
        ],
        "bea": [
            r"Account Number 戶口號碼",
            r"Statement Period 結 單 期",
            r"ACCOUNT ACTIVITIES 賬戶交易紀錄",
            r"PORTFOLIO SUMMARY 財務組合摘要",
            r"BEA東亞銀行",
            r"Bank of East Asia",
            r"東亞銀行",
        ],
        "dbs": [
            r"星展銀行",
            r"DBS Bank",
            r"DBS\s",
            r"Development Bank of Singapore",
        ],
        "hangseng": [
            r"恒生銀行",
            r"HANG SENG BANK",
            r"Hang Seng Bank",
            r"恒生",
        ],
        "hsbc": [
            r"HSBC",
            r"滙豐",
            r"Hongkong and Shanghai Banking",
            r"香港上海滙豐銀行",
        ],
    }

    @classmethod
    def detect_from_pdf(cls, pdf_path: str) -> Tuple[Optional[str], str]:
        """
        Detect bank type from PDF file.

        Returns:
            Tuple of (bank_type, extracted_text_sample)
            bank_type is None if detection fails
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                # Extract text from first few pages
                text = ""
                for i, page in enumerate(pdf.pages[:3]):
                    page_text = page.extract_text() or ""
                    text += page_text + "\n"

                return cls.detect_from_text(text), text[:500]
        except Exception as e:
            return None, f"Error reading PDF: {str(e)}"

    @classmethod
    def detect_from_text(cls, text: str) -> Optional[str]:
        """Detect bank type from extracted text."""
        for bank_type, patterns in cls.BANK_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return bank_type
        return None

    @classmethod
    def get_supported_banks(cls) -> list:
        """Return list of supported bank types."""
        return list(cls.BANK_PATTERNS.keys())
