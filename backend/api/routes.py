import os
import uuid
import tempfile
import shutil
from typing import List, Dict
from pathlib import Path
from decimal import Decimal
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from core.detector import BankDetector
from core.transaction import Transaction
from core.models import (
    FileInfo,
    FileUploadResponse,
    ParseRequest,
    ParseResponse,
    PreviewResponse,
    ExportRequest,
    TransactionData,
    TransactionSummary,
    NatureOptionsResponse,
    NATURE_OPTIONS,
)
from parsers import get_parser
from exporters.excel_exporter import ExcelExporter

router = APIRouter(prefix="/api")

# In-memory session storage (use Redis in production)
sessions: Dict[str, dict] = {}


def get_temp_dir() -> Path:
    """Get or create temp directory for uploads."""
    temp_dir = Path(tempfile.gettempdir()) / "bank_statement_converter"
    temp_dir.mkdir(exist_ok=True)
    return temp_dir


def extract_customer_name_from_pdf(pdf_path: str, bank_type: str) -> str:
    """Extract customer name from PDF using the appropriate parser."""
    if not bank_type:
        return ""
    try:
        parser = get_parser(bank_type)
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""
            return parser.extract_customer_name(first_page_text)
    except Exception:
        return ""


@router.post("/upload", response_model=FileUploadResponse)
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload one or more PDF bank statements."""
    session_id = str(uuid.uuid4())
    temp_dir = get_temp_dir() / session_id
    temp_dir.mkdir(exist_ok=True)

    file_infos = []

    for uploaded_file in files:
        file_id = str(uuid.uuid4())
        filename = uploaded_file.filename or f"file_{file_id}.pdf"

        # Save file
        file_path = temp_dir / f"{file_id}_{filename}"
        with open(file_path, "wb") as f:
            content = await uploaded_file.read()
            f.write(content)

        # Detect bank type
        bank_type, _ = BankDetector.detect_from_pdf(str(file_path))

        # Extract customer name from statement
        customer_name = extract_customer_name_from_pdf(str(file_path), bank_type) if bank_type else ""

        file_info = FileInfo(
            id=file_id,
            filename=filename,
            bank_type=bank_type,
            customer_name=customer_name,
            status="pending" if bank_type else "error",
            error_message=None if bank_type else "Could not detect bank type",
            selected=True,
        )
        file_infos.append(file_info)

    # Store session data
    sessions[session_id] = {
        "files": {f.id: f.model_dump() for f in file_infos},
        "temp_dir": str(temp_dir),
        "transactions": [],
    }

    return FileUploadResponse(files=file_infos, session_id=session_id)


@router.post("/parse", response_model=ParseResponse)
async def parse_files(request: ParseRequest, session_id: str):
    """Parse uploaded files and extract transactions."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    temp_dir = Path(session["temp_dir"])
    all_transactions: List[Transaction] = []

    for file_id in request.file_ids:
        if file_id not in session["files"]:
            continue

        file_info = session["files"][file_id]
        bank_type = file_info.get("bank_type")

        if not bank_type:
            continue

        # Find the file
        file_path = None
        for f in temp_dir.iterdir():
            if f.name.startswith(file_id):
                file_path = f
                break

        if not file_path:
            continue

        try:
            parser = get_parser(bank_type)
            transactions = parser.parse(str(file_path))

            # If customer_name override provided, use it; otherwise keep extracted name
            if request.customer_name:
                for t in transactions:
                    t.customer_name = request.customer_name
            # Otherwise, transactions already have customer_name from parser

            all_transactions.extend(transactions)
            session["files"][file_id]["status"] = "parsed"
        except Exception as e:
            session["files"][file_id]["status"] = "error"
            session["files"][file_id]["error_message"] = str(e)

    # Store transactions in session
    session["transactions"] = [t.to_dict() for t in all_transactions]

    # Calculate summary
    bank_in = [t for t in all_transactions if t.transaction_type == "in"]
    bank_out = [t for t in all_transactions if t.transaction_type == "out"]

    total_in = sum(t.amount for t in bank_in)
    total_out = sum(t.amount for t in bank_out)
    currencies = list(set(t.currency for t in all_transactions))

    summary = TransactionSummary(
        bank_in_count=len(bank_in),
        bank_out_count=len(bank_out),
        total_in=str(total_in),
        total_out=str(total_out),
        currencies=currencies,
    )

    return ParseResponse(
        transactions=[TransactionData(**t.to_dict()) for t in all_transactions],
        summary=summary,
        session_id=session_id,
    )


@router.get("/preview/{session_id}", response_model=PreviewResponse)
async def preview_transactions(session_id: str):
    """Get parsed transactions for preview."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    transactions = [Transaction.from_dict(t) for t in session.get("transactions", [])]

    bank_in = [t for t in transactions if t.transaction_type == "in"]
    bank_out = [t for t in transactions if t.transaction_type == "out"]

    # Sort by date
    bank_in.sort(key=lambda t: t.date)
    bank_out.sort(key=lambda t: t.date)

    total_in = sum(t.amount for t in bank_in)
    total_out = sum(t.amount for t in bank_out)
    currencies = list(set(t.currency for t in transactions))

    summary = TransactionSummary(
        bank_in_count=len(bank_in),
        bank_out_count=len(bank_out),
        total_in=str(total_in),
        total_out=str(total_out),
        currencies=currencies,
    )

    return PreviewResponse(
        bank_in=[TransactionData(**t.to_dict()) for t in bank_in],
        bank_out=[TransactionData(**t.to_dict()) for t in bank_out],
        summary=summary,
    )


@router.post("/export")
async def export_excel(request: ExportRequest):
    """Generate and download Excel file."""
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[request.session_id]
    transactions = [Transaction.from_dict(t) for t in session.get("transactions", [])]

    if not transactions:
        raise HTTPException(status_code=400, detail="No transactions to export")

    # Apply customer name
    for t in transactions:
        t.customer_name = request.customer_name

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    customer_suffix = f"_{request.customer_name}" if request.customer_name else ""
    filename = f"accounting_queries{customer_suffix}_{timestamp}.xlsx"

    # Create Excel file
    temp_dir = Path(session["temp_dir"])
    output_path = temp_dir / filename

    exporter = ExcelExporter()
    exporter.export(transactions, str(output_path), request.customer_name)

    return FileResponse(
        path=str(output_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/nature-options", response_model=NatureOptionsResponse)
async def get_nature_options():
    """Get list of Nature dropdown values."""
    return NatureOptionsResponse(options=["Please Select"] + NATURE_OPTIONS)


@router.put("/transactions/{session_id}")
async def update_transaction(session_id: str, transaction_index: int, nature: str = "", remark: str = ""):
    """Update a transaction's nature or remark."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    transactions = session.get("transactions", [])

    if transaction_index < 0 or transaction_index >= len(transactions):
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Update the transaction
    if nature:
        transactions[transaction_index]["nature"] = nature
    if remark is not None:
        transactions[transaction_index]["remark"] = remark

    return {"status": "updated", "index": transaction_index}


@router.put("/transactions/{session_id}/bulk")
async def update_transactions_bulk(session_id: str, updates: List[dict]):
    """Bulk update transaction nature/remark values.

    updates: List of {index: int, nature?: str, remark?: str}
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    transactions = session.get("transactions", [])

    for update in updates:
        idx = update.get("index")
        if idx is not None and 0 <= idx < len(transactions):
            if "nature" in update:
                transactions[idx]["nature"] = update["nature"]
            if "remark" in update:
                transactions[idx]["remark"] = update["remark"]

    return {"status": "updated", "count": len(updates)}


@router.delete("/session/{session_id}")
async def cleanup_session(session_id: str):
    """Clean up session data and temporary files."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    temp_dir = Path(session["temp_dir"])

    # Remove temp files
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    # Remove session
    del sessions[session_id]

    return {"status": "cleaned"}


@router.get("/supported-banks")
async def get_supported_banks():
    """Get list of supported bank types."""
    return {"banks": BankDetector.get_supported_banks()}
