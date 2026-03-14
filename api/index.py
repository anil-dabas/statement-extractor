from http.server import BaseHTTPRequestHandler
import os
import sys
import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from urllib.parse import parse_qs, urlparse

# Add backend to path
backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend')
sys.path.insert(0, backend_path)

from core.detector import BankDetector
from core.transaction import Transaction
from parsers import get_parser
from exporters.excel_exporter import ExcelExporter

TEMP_DIR = Path('/tmp/bank_statement_converter')


def load_session(session_id):
    """Load session data from file."""
    session_file = TEMP_DIR / session_id / "session.json"
    if session_file.exists():
        with open(session_file, 'r') as f:
            return json.load(f)
    return None


def save_session(session_id, session_data):
    """Save session data to file."""
    session_dir = TEMP_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / "session.json"
    with open(session_file, 'w') as f:
        json.dump(session_data, f)

NATURE_OPTIONS = [
    "Salary", "Rental Income", "Investment Income", "Business Income",
    "Transfer In", "Loan", "Other Income", "Rent", "Utilities",
    "Office Expenses", "Professional Fees", "Bank Charges",
    "Transfer Out", "Loan Repayment", "Other Expenses",
]


def get_session_dir(session_id):
    session_dir = TEMP_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def extract_customer_name_from_pdf(pdf_path, bank_type):
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


class handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_error(self, message, status=400):
        self._send_json({"error": message}, status)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/api/supported-banks':
            self._send_json({"banks": BankDetector.get_supported_banks()})
        elif path == '/api/nature-options':
            self._send_json({"options": ["Please Select"] + NATURE_OPTIONS})
        else:
            self._send_error("Not found", 404)

    def do_DELETE(self):
        path = urlparse(self.path).path

        if path.startswith('/api/session/'):
            session_id = path.split('/')[-1]
            session = load_session(session_id)
            if session:
                temp_dir = Path(session["temp_dir"])
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                self._send_json({"status": "cleaned"})
            else:
                self._send_error("Session not found", 404)
        else:
            self._send_error("Not found", 404)

    def do_POST(self):
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)
        content_length = int(self.headers.get('Content-Length', 0))
        content_type = self.headers.get('Content-Type', '')

        try:
            if path == '/api/upload':
                self._handle_upload(content_type, content_length)
            elif path == '/api/parse':
                session_id = query.get('session_id', [None])[0]
                if not session_id:
                    self._send_error("session_id required", 400)
                    return
                body = json.loads(self.rfile.read(content_length))
                self._handle_parse(session_id, body)
            elif path == '/api/export':
                body = json.loads(self.rfile.read(content_length))
                self._handle_export(body)
            else:
                self._send_error("Not found", 404)
        except Exception as e:
            self._send_error(str(e), 500)

    def _handle_upload(self, content_type, content_length):
        if 'multipart/form-data' not in content_type:
            self._send_error("Expected multipart/form-data", 400)
            return

        body = self.rfile.read(content_length)
        boundary = content_type.split('boundary=')[1] if 'boundary=' in content_type else None
        if not boundary:
            self._send_error("No boundary", 400)
            return

        session_id = str(uuid.uuid4())
        session_dir = get_session_dir(session_id)
        file_infos = []
        all_transactions = []

        import re
        parts = body.split(f'--{boundary}'.encode())
        for part in parts:
            if b'filename="' in part:
                header_end = part.find(b'\r\n\r\n')
                if header_end == -1:
                    continue
                header = part[:header_end].decode('utf-8', errors='ignore')
                file_content = part[header_end + 4:]

                for suffix in [b'\r\n', b'--', b'\r\n']:
                    if file_content.endswith(suffix):
                        file_content = file_content[:-len(suffix)]

                filename_match = re.search(r'filename="([^"]+)"', header)
                filename = filename_match.group(1) if filename_match else f"file_{uuid.uuid4()}.pdf"

                file_id = str(uuid.uuid4())
                file_path = session_dir / f"{file_id}_{filename}"

                with open(file_path, 'wb') as f:
                    f.write(file_content)

                bank_type, _ = BankDetector.detect_from_pdf(str(file_path))
                customer_name = extract_customer_name_from_pdf(str(file_path), bank_type) if bank_type else ""

                file_info = {
                    "id": file_id,
                    "filename": filename,
                    "bank_type": bank_type,
                    "customer_name": customer_name,
                    "status": "pending" if bank_type else "error",
                    "error_message": None if bank_type else "Could not detect bank type",
                    "selected": True
                }

                # Parse immediately if bank type detected
                if bank_type:
                    try:
                        parser = get_parser(bank_type)
                        transactions = parser.parse(str(file_path))
                        for t in transactions:
                            if customer_name:
                                t.customer_name = customer_name
                        all_transactions.extend(transactions)
                        file_info["status"] = "parsed"
                    except Exception as e:
                        file_info["status"] = "error"
                        file_info["error_message"] = str(e)

                file_infos.append(file_info)

        # Calculate summary
        bank_in = [t for t in all_transactions if t.transaction_type == "in"]
        bank_out = [t for t in all_transactions if t.transaction_type == "out"]

        session_data = {
            "files": {f["id"]: f for f in file_infos},
            "temp_dir": str(session_dir),
            "transactions": [t.to_dict() for t in all_transactions]
        }
        save_session(session_id, session_data)

        self._send_json({
            "files": file_infos,
            "session_id": session_id,
            "transactions": [t.to_dict() for t in all_transactions],
            "summary": {
                "bank_in_count": len(bank_in),
                "bank_out_count": len(bank_out),
                "total_in": str(sum(t.amount for t in bank_in)),
                "total_out": str(sum(t.amount for t in bank_out)),
                "currencies": list(set(t.currency for t in all_transactions))
            }
        })

    def _handle_parse(self, session_id, body):
        session = load_session(session_id)
        if not session:
            self._send_error("Session not found", 404)
            return

        temp_dir = Path(session["temp_dir"])
        all_transactions = []

        file_ids = body.get("file_ids", [])
        customer_name_override = body.get("customer_name", "")

        for file_id in file_ids:
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
                if customer_name_override:
                    for t in transactions:
                        t.customer_name = customer_name_override
                all_transactions.extend(transactions)
                session["files"][file_id]["status"] = "parsed"
            except Exception as e:
                session["files"][file_id]["status"] = "error"
                session["files"][file_id]["error_message"] = str(e)

        session["transactions"] = [t.to_dict() for t in all_transactions]
        save_session(session_id, session)

        bank_in = [t for t in all_transactions if t.transaction_type == "in"]
        bank_out = [t for t in all_transactions if t.transaction_type == "out"]

        self._send_json({
            "transactions": [t.to_dict() for t in all_transactions],
            "summary": {
                "bank_in_count": len(bank_in),
                "bank_out_count": len(bank_out),
                "total_in": str(sum(t.amount for t in bank_in)),
                "total_out": str(sum(t.amount for t in bank_out)),
                "currencies": list(set(t.currency for t in all_transactions))
            },
            "session_id": session_id
        })

    def _handle_export(self, body):
        session_id = body.get("session_id")
        customer_name = body.get("customer_name", "")
        transactions_data = body.get("transactions", [])

        # Try to load from session first, fall back to request body
        if transactions_data:
            transactions = [Transaction.from_dict(t) for t in transactions_data]
        else:
            session = load_session(session_id)
            if not session:
                self._send_error("Session not found and no transactions provided", 404)
                return
            transactions = [Transaction.from_dict(t) for t in session.get("transactions", [])]

        if not transactions:
            self._send_error("No transactions to export", 400)
            return

        for t in transactions:
            if customer_name:
                t.customer_name = customer_name

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"accounting_queries_{customer_name}_{timestamp}.xlsx" if customer_name else f"accounting_queries_{timestamp}.xlsx"

        # Use a temp file for export
        temp_dir = TEMP_DIR / str(uuid.uuid4())
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = temp_dir / filename

        exporter = ExcelExporter()
        exporter.export(transactions, str(output_path), customer_name)

        with open(output_path, "rb") as f:
            content = f.read()

        # Cleanup temp file
        shutil.rmtree(temp_dir, ignore_errors=True)

        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content)
