from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal


class FileInfo(BaseModel):
    """Information about an uploaded file."""

    id: str
    filename: str
    bank_type: Optional[str] = None
    customer_name: str = ""  # Extracted from statement
    status: str = "pending"  # pending, parsed, error
    error_message: Optional[str] = None
    selected: bool = True  # Whether to include in processing


class FileUploadResponse(BaseModel):
    """Response for file upload endpoint."""

    files: List[FileInfo]
    session_id: str


class ParseRequest(BaseModel):
    """Request to parse uploaded files."""

    file_ids: List[str]
    customer_name: str = ""


class TransactionData(BaseModel):
    """Transaction data for API responses."""

    date: str
    amount: str
    currency: str
    description: str
    transaction_type: str
    bank_name: str
    exchange_rate: str = ""
    nature: str = ""
    remark: str = ""
    customer_name: str = ""


class TransactionSummary(BaseModel):
    """Summary of parsed transactions."""

    bank_in_count: int
    bank_out_count: int
    total_in: str
    total_out: str
    currencies: List[str]


class ParseResponse(BaseModel):
    """Response for parse endpoint."""

    transactions: List[TransactionData]
    summary: TransactionSummary
    session_id: str


class PreviewResponse(BaseModel):
    """Response for preview endpoint."""

    bank_in: List[TransactionData]
    bank_out: List[TransactionData]
    summary: TransactionSummary


class ExportRequest(BaseModel):
    """Request to export transactions to Excel."""

    session_id: str
    customer_name: str = ""
    year: Optional[int] = None


class NatureOptionsResponse(BaseModel):
    """Response for nature options endpoint."""

    options: List[str]


# Nature dropdown values
NATURE_OPTIONS = [
    "Consulting Income",
    "Consulting Fee",
    "Audit Fee",
    "Audit fee",
    "Bank Charges",
    "Entertainment",
    "Travelling Exp",
    "Overseas Travelling",
    "Print & Stationery",
    "Tel & Internet",
    "Company Secretary Fee",
    "Consulting Fee - Talent Fields",
    "Director Current Account",
    "Others - Please Specific",
]
