import { useState, useCallback } from 'react';
import FileUpload from './components/FileUpload';
import StatementList from './components/StatementList';
import TransactionPreview from './components/TransactionPreview';
import ExportButton from './components/ExportButton';
import type { FileInfo, Transaction, TransactionSummary } from './types';
import { uploadFiles } from './services/api';

function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [transactions, setTransactions] = useState<{
    bank_in: Transaction[];
    bank_out: Transaction[];
  }>({ bank_in: [], bank_out: [] });
  const [summary, setSummary] = useState<TransactionSummary | null>(null);
  const [customerName, setCustomerName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<'upload' | 'preview' | 'export'>('upload');

  const handleFilesSelected = useCallback(async (selectedFiles: File[]) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await uploadFiles(selectedFiles);
      setSessionId(response.session_id);
      setFiles(response.files);

      // Store parsed transactions from upload response
      if (response.transactions && response.transactions.length > 0) {
        const bankIn = response.transactions.filter((t: Transaction) => t.transaction_type === 'in');
        const bankOut = response.transactions.filter((t: Transaction) => t.transaction_type === 'out');
        setTransactions({ bank_in: bankIn, bank_out: bankOut });
        if (response.summary) {
          setSummary(response.summary);
        }
      }

      setStep('preview');
    } catch (err) {
      setError('Failed to upload files. Please try again.');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleToggleFileSelect = useCallback((fileId: string) => {
    setFiles(prev => prev.map(f =>
      f.id === fileId ? { ...f, selected: !f.selected } : f
    ));
  }, []);

  const handleParse = useCallback(async () => {
    if (!sessionId || files.length === 0) return;

    setIsLoading(true);
    setError(null);

    try {
      const validFiles = files.filter((f) => f.selected && f.bank_type && f.status !== 'error');

      if (validFiles.length === 0) {
        setError('Please select at least one valid file to process.');
        setIsLoading(false);
        return;
      }

      // Transactions are already parsed during upload, just proceed to export
      // Filter transactions based on selected files if needed
      if (transactions.bank_in.length === 0 && transactions.bank_out.length === 0) {
        setError('No transactions found. Please re-upload the files.');
        setIsLoading(false);
        return;
      }

      setStep('export');
    } catch (err) {
      setError('Failed to process files. Please try again.');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, files, transactions]);

  const handleReset = useCallback(() => {
    setSessionId(null);
    setFiles([]);
    setTransactions({ bank_in: [], bank_out: [] });
    setSummary(null);
    setCustomerName('');
    setError(null);
    setStep('upload');
  }, []);

  // Get unique customer names from selected files
  const selectedCustomerNames = [...new Set(
    files
      .filter(f => f.selected && f.customer_name)
      .map(f => f.customer_name)
  )];

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <h1 className="text-2xl font-bold text-gray-900">
            Bank Statement Converter
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Convert bank statements to Accounting Queries format
          </p>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
            {error}
          </div>
        )}

        {/* Step Indicator */}
        <div className="mb-8">
          <div className="flex items-center justify-center space-x-4">
            {['upload', 'preview', 'export'].map((s, i) => (
              <div key={s} className="flex items-center">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                    step === s
                      ? 'bg-blue-600 text-white'
                      : i < ['upload', 'preview', 'export'].indexOf(step)
                      ? 'bg-green-500 text-white'
                      : 'bg-gray-200 text-gray-600'
                  }`}
                >
                  {i + 1}
                </div>
                <span className="ml-2 text-sm font-medium text-gray-700 capitalize">
                  {s}
                </span>
                {i < 2 && (
                  <div className="w-16 h-0.5 bg-gray-200 mx-4" />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Upload Step */}
        {step === 'upload' && (
          <div className="bg-white rounded-lg shadow p-6">
            <FileUpload
              onFilesSelected={handleFilesSelected}
              isLoading={isLoading}
            />
          </div>
        )}

        {/* Preview Step */}
        {step === 'preview' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">Uploaded Files</h2>
              <StatementList
                files={files}
                onToggleSelect={handleToggleFileSelect}
                showSelection={true}
              />

              <div className="mt-6 pt-6 border-t border-gray-200">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Customer Name for Export
                  {selectedCustomerNames.length === 1 && (
                    <span className="text-gray-500 font-normal ml-2">
                      (detected: {selectedCustomerNames[0]})
                    </span>
                  )}
                </label>
                <input
                  type="text"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  className="w-full max-w-md px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder={selectedCustomerNames[0] || "Enter customer name (optional - will use detected names if empty)"}
                />
                <p className="mt-1 text-xs text-gray-500">
                  Leave empty to use customer names detected from statements, or enter a name to override all.
                </p>
              </div>

              <div className="mt-6 flex space-x-4">
                <button
                  onClick={handleReset}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
                >
                  Start Over
                </button>
                <button
                  onClick={handleParse}
                  disabled={isLoading || files.filter(f => f.selected && f.bank_type).length === 0}
                  className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                >
                  {isLoading ? 'Processing...' : 'Parse Selected Statements'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Export Step */}
        {step === 'export' && sessionId && summary && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className="text-lg font-semibold">Transaction Summary</h2>
                  <p className="text-sm text-gray-500 mt-1">
                    {summary.bank_in_count} deposits, {summary.bank_out_count}{' '}
                    withdrawals
                  </p>
                </div>
                <div className="flex space-x-4">
                  <button
                    onClick={handleReset}
                    className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
                  >
                    Start Over
                  </button>
                  <ExportButton
                    sessionId={sessionId}
                    customerName={customerName}
                    transactions={[...transactions.bank_in, ...transactions.bank_out]}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 mb-6">
                <div className="bg-green-50 rounded-lg p-4">
                  <p className="text-sm text-green-600 font-medium">
                    Total Bank In
                  </p>
                  <p className="text-2xl font-bold text-green-700">
                    {parseFloat(summary.total_in).toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </p>
                  {summary.currencies.length > 0 && (
                    <p className="text-xs text-green-600 mt-1">
                      Currencies: {summary.currencies.join(', ')}
                    </p>
                  )}
                </div>
                <div className="bg-red-50 rounded-lg p-4">
                  <p className="text-sm text-red-600 font-medium">
                    Total Bank Out
                  </p>
                  <p className="text-2xl font-bold text-red-700">
                    {parseFloat(summary.total_out).toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </p>
                  {summary.currencies.length > 0 && (
                    <p className="text-xs text-red-600 mt-1">
                      Currencies: {summary.currencies.join(', ')}
                    </p>
                  )}
                </div>
              </div>

              {/* Customer name override for export */}
              <div className="mb-6 p-4 bg-gray-50 rounded-lg">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Customer Name for Export
                </label>
                <input
                  type="text"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  className="w-full max-w-md px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Enter customer name to override all transactions"
                />
                <p className="mt-1 text-xs text-gray-500">
                  If provided, this name will be used for all transactions in the export.
                </p>
              </div>

              <TransactionPreview
                bankIn={transactions.bank_in}
                bankOut={transactions.bank_out}
                sessionId={sessionId}
                onTransactionsUpdate={(bankIn, bankOut) => {
                  setTransactions({ bank_in: bankIn, bank_out: bankOut });
                }}
              />
            </div>
          </div>
        )}
      </main>

      <footer className="bg-white border-t mt-auto">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <p className="text-sm text-gray-500 text-center">
            Supported banks: Airwallex, BEA, DBS, Hang Seng, HSBC
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;
