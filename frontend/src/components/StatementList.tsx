import { FileText, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import type { FileInfo } from '../types';

interface StatementListProps {
  files: FileInfo[];
  onToggleSelect?: (fileId: string) => void;
  showSelection?: boolean;
}

const bankNames: Record<string, string> = {
  airwallex: 'Airwallex',
  bea: 'Bank of East Asia',
  dbs: 'DBS Bank',
  hangseng: 'Hang Seng Bank',
  hsbc: 'HSBC',
};

function StatementList({ files, onToggleSelect, showSelection = true }: StatementListProps) {
  if (files.length === 0) {
    return (
      <p className="text-gray-500 text-center py-4">No files uploaded yet.</p>
    );
  }

  // Group files by customer name
  const customerGroups = files.reduce((groups, file) => {
    const name = file.customer_name || 'Unknown Customer';
    if (!groups[name]) {
      groups[name] = [];
    }
    groups[name].push(file);
    return groups;
  }, {} as Record<string, FileInfo[]>);

  const hasMultipleCustomers = Object.keys(customerGroups).length > 1;

  return (
    <div className="space-y-4">
      {hasMultipleCustomers && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
          <p className="text-sm text-yellow-800">
            Multiple customers detected. Select the files you want to process.
          </p>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              {showSelection && (
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-12">
                  Select
                </th>
              )}
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                File
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Customer Name
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Bank Type
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {files.map((file) => (
              <tr
                key={file.id}
                className={!file.selected && showSelection ? 'bg-gray-50 opacity-60' : ''}
              >
                {showSelection && (
                  <td className="px-4 py-4 whitespace-nowrap">
                    <input
                      type="checkbox"
                      checked={file.selected}
                      onChange={() => onToggleSelect?.(file.id)}
                      disabled={file.status === 'error'}
                      className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                    />
                  </td>
                )}
                <td className="px-4 py-4 whitespace-nowrap">
                  <div className="flex items-center">
                    <FileText className="w-5 h-5 text-gray-400 mr-3" />
                    <span className="text-sm text-gray-900">{file.filename}</span>
                  </div>
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  {file.customer_name ? (
                    <span className="text-sm font-medium text-gray-900">
                      {file.customer_name}
                    </span>
                  ) : (
                    <span className="text-sm text-gray-400 italic">
                      Not detected
                    </span>
                  )}
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  {file.bank_type ? (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                      {bankNames[file.bank_type] || file.bank_type}
                    </span>
                  ) : (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                      Unknown
                    </span>
                  )}
                </td>
                <td className="px-4 py-4 whitespace-nowrap">
                  {file.status === 'parsed' && (
                    <span className="inline-flex items-center text-green-600">
                      <CheckCircle className="w-4 h-4 mr-1" />
                      <span className="text-sm">Parsed</span>
                    </span>
                  )}
                  {file.status === 'pending' && (
                    <span className="inline-flex items-center text-yellow-600">
                      <AlertCircle className="w-4 h-4 mr-1" />
                      <span className="text-sm">Ready</span>
                    </span>
                  )}
                  {file.status === 'error' && (
                    <span className="inline-flex items-center text-red-600">
                      <XCircle className="w-4 h-4 mr-1" />
                      <span className="text-sm">
                        {file.error_message || 'Error'}
                      </span>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showSelection && (
        <p className="text-xs text-gray-500">
          {files.filter(f => f.selected).length} of {files.length} files selected
        </p>
      )}
    </div>
  );
}

export default StatementList;
