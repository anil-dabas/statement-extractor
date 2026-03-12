"""Vercel serverless function - FastAPI app with ASGI handler."""
import os
import sys

# Add backend to path BEFORE importing anything else
backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend')
sys.path.insert(0, backend_path)

import uuid
import json
import shutil
from typing import List, Dict
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from mangum import Mangum

from core.detector import BankDetector
from core.transaction import Transaction
from parsers import get_parser
from exporters.excel_exporter import ExcelExporter

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Temp directory for serverless
TEMP_DIR = Path('/tmp/bank_statement_converter')

# In-memory sessions
sessions: Dict[str, dict] = {}


# Pydantic models
class FileInfo(BaseModel):
    id: str
    filename: str
    bank_type: str | None
    customer_name: str
    status: str
    error_message: str | None
    selected: bool


class FileUploadResponse(BaseModel):
    files: List[FileInfo]
    session_id: str


class ParseRequest(BaseModel):
    file_ids: List[str]
    customer_name: str = ""


class TransactionData(BaseModel):
    date: str
    amount: str
    currency: str
    description: str
    transaction_type: str
    bank_name: str
    customer_name: str
    nature: str
    remark: str
    exchange_rate: str | None


class TransactionSummary(BaseModel):
    bank_in_count: int
    bank_out_count: int
    total_in: str
    total_out: str
    currencies: List[str]


class ParseResponse(BaseModel):
    transactions: List[TransactionData]
    summary: TransactionSummary
    session_id: str


class ExportRequest(BaseModel):
    session_id: str
    customer_name: str = ""


NATURE_OPTIONS = [
    "Salary", "Rental Income", "Investment Income", "Business Income",
    "Transfer In", "Loan", "Other Income", "Rent", "Utilities",
    "Office Expenses", "Professional Fees", "Bank Charges",
    "Transfer Out", "Loan Repayment", "Other Expenses",
]


def get_session_dir(session_id: str) -> Path:
    session_dir = TEMP_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def extract_customer_name_from_pdf(pdf_path: str, bank_type: str) -> str:
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


@app.post("/api/upload", response_model=FileUploadResponse)
async def upload_files(files: List[UploadFile] = File(...)):
    session_id = str(uuid.uuid4())
    session_dir = get_session_dir(session_id)
    file_infos = []

    for uploaded_file in files:
        file_id = str(uuid.uuid4())
        filename = uploaded_file.filename or f"file_{file_id}.pdf"
        file_path = session_dir / f"{file_id}_{filename}"
        content = await uploaded_file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        bank_type, _ = BankDetector.detect_from_pdf(str(file_path))
        customer_name = extract_customer_name_from_pdf(str(file_path), bank_type) if bank_type else ""

        file_info = FileInfo(
            id=file_id, filename=filename, bank_type=bank_type,
            customer_name=customer_name,
            status="pending" if bank_type else "error",
            error_message=None if bank_type else "Could not detect bank type",
            selected=True,
        )
        file_infos.append(file_info)

    sessions[session_id] = {
        "files": {f.id: f.model_dump() for f in file_infos},
        "temp_dir": str(session_dir),
        "transactions": [],
    }
    return FileUploadResponse(files=file_infos, session_id=session_id)


@app.post("/api/parse", response_model=ParseResponse)
async def parse_files(request: ParseRequest, session_id: str = Query(...)):
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
            if request.customer_name:
                for t in transactions:
                    t.customer_name = request.customer_name
            all_transactions.extend(transactions)
            session["files"][file_id]["status"] = "parsed"
        except Exception as e:
            session["files"][file_id]["status"] = "error"
            session["files"][file_id]["error_message"] = str(e)

    session["transactions"] = [t.to_dict() for t in all_transactions]

    bank_in = [t for t in all_transactions if t.transaction_type == "in"]
    bank_out = [t for t in all_transactions if t.transaction_type == "out"]

    summary = TransactionSummary(
        bank_in_count=len(bank_in), bank_out_count=len(bank_out),
        total_in=str(sum(t.amount for t in bank_in)),
        total_out=str(sum(t.amount for t in bank_out)),
        currencies=list(set(t.currency for t in all_transactions)),
    )

    return ParseResponse(
        transactions=[TransactionData(**t.to_dict()) for t in all_transactions],
        summary=summary, session_id=session_id,
    )


@app.post("/api/export")
async def export_excel(request: ExportRequest):
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[request.session_id]
    transactions = [Transaction.from_dict(t) for t in session.get("transactions", [])]

    if not transactions:
        raise HTTPException(status_code=400, detail="No transactions to export")

    for t in transactions:
        t.customer_name = request.customer_name

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    customer_suffix = f"_{request.customer_name}" if request.customer_name else ""
    filename = f"accounting_queries{customer_suffix}_{timestamp}.xlsx"

    temp_dir = Path(session["temp_dir"])
    output_path = temp_dir / filename

    exporter = ExcelExporter()
    exporter.export(transactions, str(output_path), request.customer_name)

    with open(output_path, "rb") as f:
        content = f.read()

    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/nature-options")
async def get_nature_options():
    return {"options": ["Please Select"] + NATURE_OPTIONS}


@app.get("/api/supported-banks")
async def get_supported_banks():
    return {"banks": BankDetector.get_supported_banks()}


@app.delete("/api/session/{session_id}")
async def cleanup_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    temp_dir = Path(session["temp_dir"])
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    del sessions[session_id]
    return {"status": "cleaned"}


# Vercel handler
handler = Mangum(app, lifespan="off")
