# Bank Statement Converter

A full-stack application that converts multiple bank statement formats into a standardized "Accounting Queries" Excel format.

## Features

- **Multi-bank support**: Airwallex, BEA, DBS, Hang Seng, HSBC
- **Automatic bank detection**: Identifies bank type from PDF content
- **Merged output**: Combines multiple statements into single Excel file
- **Categorized sheets**: Separate "Bank In" and "Bank Out" sheets
- **Nature dropdown**: Pre-populated dropdown for transaction classification
- **Both Web and Desktop interfaces**

## Supported Banks

| Bank | Date Format | Identifier |
|------|-------------|------------|
| Airwallex | Dec 02 2025 | airwallex.com |
| BEA | 11DEC25 | BEA東亞銀行 |
| DBS | 10-May-22 | 星展銀行, DBS Bank |
| Hang Seng | 29 Nov | 恒生銀行, HANG SENG BANK |
| HSBC | 22 May | HSBC, 滙豐 |

## Output Format

### Excel Structure
- **Sheet 1: "Bank In"** - All credit/deposit transactions
- **Sheet 2: "Bank Out"** - All debit/withdrawal transactions
- **Sheet 3: "Sheet3"** - Nature dropdown values

### Columns
| Customer Name | Date | Amount | Currency | Exchange Rate | Description | Nature | Remark |

### Nature Options
- Consulting Income
- Consulting Fee
- Audit Fee
- Bank Charges
- Entertainment
- Travelling Exp
- Overseas Travelling
- Print & Stationery
- Tel & Internet
- Company Secretary Fee
- Consulting Fee - Talent Fields
- Director Current Account
- Others - Please Specific

## Installation

### Prerequisites
- Python 3.9+
- Node.js 18+
- npm or yarn

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Frontend Setup

```bash
cd frontend
npm install
```

### Desktop Setup (Optional)

```bash
cd desktop
npm install
```

## Running the Application

### Development Mode

**Terminal 1 - Backend:**
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

Then open http://localhost:3000 in your browser.

### Desktop App

```bash
cd desktop
npm run dev
```

### Production Build

**Build Frontend:**
```bash
cd frontend
npm run build
```

**Run Production Server:**
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Build Desktop App:**
```bash
cd desktop
npm run build
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/upload | Upload PDF bank statements |
| POST | /api/parse | Parse uploaded files |
| GET | /api/preview/{session_id} | Preview parsed transactions |
| POST | /api/export | Generate Excel file |
| GET | /api/nature-options | Get nature dropdown values |
| GET | /api/supported-banks | List supported banks |
| DELETE | /api/session/{session_id} | Cleanup session |

## Project Structure

```
bank_statement_converter/
├── backend/                    # Python FastAPI Backend
│   ├── main.py                # FastAPI app entry
│   ├── requirements.txt
│   ├── core/
│   │   ├── detector.py        # Bank type detection
│   │   ├── transaction.py     # Transaction data model
│   │   └── models.py          # Pydantic models
│   ├── parsers/
│   │   ├── base_parser.py     # Abstract parser
│   │   ├── airwallex_parser.py
│   │   ├── bea_parser.py
│   │   ├── dbs_parser.py
│   │   ├── hangseng_parser.py
│   │   └── hsbc_parser.py
│   ├── exporters/
│   │   └── excel_exporter.py  # Generate Excel output
│   └── api/
│       └── routes.py          # API endpoints
│
├── frontend/                   # React Frontend
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── FileUpload.tsx
│   │   │   ├── StatementList.tsx
│   │   │   ├── TransactionPreview.tsx
│   │   │   └── ExportButton.tsx
│   │   ├── services/
│   │   │   └── api.ts
│   │   └── types/
│   │       └── index.ts
│
├── desktop/                    # Electron Desktop App
│   ├── package.json
│   ├── main.js
│   └── preload.js
│
└── README.md
```

## Usage

1. **Upload**: Drag and drop or select bank statement PDFs
2. **Review**: Check detected bank types and enter customer name
3. **Parse**: Process statements to extract transactions
4. **Preview**: Review Bank In and Bank Out transactions
5. **Export**: Download Excel file in Accounting Queries format

## Technology Stack

### Backend
- Python 3.9+
- FastAPI
- pdfplumber (PDF parsing)
- openpyxl (Excel generation)
- pandas

### Frontend
- React 18 + TypeScript
- Tailwind CSS
- React Query
- React Dropzone
- Axios

### Desktop
- Electron
- electron-builder

## License

Private - Talent Fields
