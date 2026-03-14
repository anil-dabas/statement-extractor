export interface FileInfo {
  id: string;
  filename: string;
  bank_type: string | null;
  customer_name: string;
  status: 'pending' | 'parsed' | 'error';
  error_message?: string;
  selected: boolean;
}

export interface UploadResponse {
  files: FileInfo[];
  session_id: string;
  transactions?: Transaction[];
  summary?: TransactionSummary;
}

export interface Transaction {
  date: string;
  amount: string;
  currency: string;
  description: string;
  transaction_type: 'in' | 'out';
  bank_name: string;
  exchange_rate: string;
  nature: string;
  remark: string;
  customer_name: string;
}

export interface TransactionSummary {
  bank_in_count: number;
  bank_out_count: number;
  total_in: string;
  total_out: string;
  currencies: string[];
}

export interface ParseResponse {
  transactions: Transaction[];
  summary: TransactionSummary;
  session_id: string;
}

export interface PreviewResponse {
  bank_in: Transaction[];
  bank_out: Transaction[];
  summary: TransactionSummary;
}

export interface ExportRequest {
  session_id: string;
  customer_name: string;
  year?: number;
  transactions?: Transaction[];
}
