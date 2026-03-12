import axios from 'axios';
import type {
  UploadResponse,
  ParseResponse,
  PreviewResponse,
  ExportRequest,
} from '../types';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
});

export async function uploadFiles(files: File[]): Promise<UploadResponse> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append('files', file);
  });

  const response = await api.post<UploadResponse>('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });

  return response.data;
}

export async function parseFiles(
  sessionId: string,
  fileIds: string[],
  customerName: string = ''
): Promise<ParseResponse> {
  const response = await api.post<ParseResponse>(
    `/parse?session_id=${sessionId}`,
    {
      file_ids: fileIds,
      customer_name: customerName,
    }
  );

  return response.data;
}

export async function getPreview(sessionId: string): Promise<PreviewResponse> {
  const response = await api.get<PreviewResponse>(`/preview/${sessionId}`);
  return response.data;
}

export async function exportExcel(request: ExportRequest): Promise<Blob> {
  const response = await api.post('/export', request, {
    responseType: 'blob',
  });
  return response.data;
}

export async function getNatureOptions(): Promise<string[]> {
  const response = await api.get<{ options: string[] }>('/nature-options');
  return response.data.options;
}

export async function getSupportedBanks(): Promise<string[]> {
  const response = await api.get<{ banks: string[] }>('/supported-banks');
  return response.data.banks;
}

export async function cleanupSession(sessionId: string): Promise<void> {
  await api.delete(`/session/${sessionId}`);
}

export async function updateTransaction(
  sessionId: string,
  transactionIndex: number,
  nature?: string,
  remark?: string
): Promise<void> {
  const params = new URLSearchParams();
  if (nature !== undefined) params.append('nature', nature);
  if (remark !== undefined) params.append('remark', remark);

  await api.put(
    `/transactions/${sessionId}?transaction_index=${transactionIndex}&${params.toString()}`
  );
}

export async function updateTransactionsBulk(
  sessionId: string,
  updates: Array<{ index: number; nature?: string; remark?: string }>
): Promise<void> {
  await api.put(`/transactions/${sessionId}/bulk`, updates);
}
