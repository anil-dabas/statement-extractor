import { useState, useMemo, useEffect, useCallback } from 'react';
import type { Transaction } from '../types';
import { getNatureOptions, updateTransactionsBulk } from '../services/api';

interface TransactionPreviewProps {
  bankIn: Transaction[];
  bankOut: Transaction[];
  sessionId: string;
  onTransactionsUpdate?: (bankIn: Transaction[], bankOut: Transaction[]) => void;
}

interface CurrencyGroup {
  currency: string;
  transactions: Array<Transaction & { globalIndex: number }>;
  total: number;
}

function TransactionPreview({ bankIn, bankOut, sessionId, onTransactionsUpdate }: TransactionPreviewProps) {
  const [activeTab, setActiveTab] = useState<'in' | 'out'>('in');
  const [natureOptions, setNatureOptions] = useState<string[]>([]);
  const [localBankIn, setLocalBankIn] = useState<Transaction[]>(bankIn);
  const [localBankOut, setLocalBankOut] = useState<Transaction[]>(bankOut);
  const [pendingChanges, setPendingChanges] = useState<Map<number, { nature?: string; remark?: string }>>(new Map());
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saved' | 'error'>('idle');

  // Fetch nature options on mount
  useEffect(() => {
    getNatureOptions().then(setNatureOptions).catch(console.error);
  }, []);

  // Sync local state with props
  useEffect(() => {
    setLocalBankIn(bankIn);
    setLocalBankOut(bankOut);
  }, [bankIn, bankOut]);

  const transactions = activeTab === 'in' ? localBankIn : localBankOut;

  // Calculate global index offset for bank_out transactions
  const getGlobalIndex = useCallback((localIndex: number, type: 'in' | 'out') => {
    return type === 'in' ? localIndex : localBankIn.length + localIndex;
  }, [localBankIn.length]);

  // Group transactions by currency (HKD first, then others alphabetically)
  const currencyGroups = useMemo((): CurrencyGroup[] => {
    const groups: Record<string, Array<Transaction & { globalIndex: number }>> = {};

    transactions.forEach((t, localIndex) => {
      if (!groups[t.currency]) {
        groups[t.currency] = [];
      }
      groups[t.currency].push({
        ...t,
        globalIndex: getGlobalIndex(localIndex, activeTab),
      });
    });

    // Sort: HKD first, then others alphabetically
    const currencies = Object.keys(groups);
    const sortedCurrencies = ['HKD', ...currencies.filter(c => c !== 'HKD').sort()];

    return sortedCurrencies
      .filter(c => groups[c])
      .map(currency => ({
        currency,
        transactions: groups[currency].sort((a, b) =>
          new Date(a.date).getTime() - new Date(b.date).getTime()
        ),
        total: groups[currency].reduce((sum, t) => sum + parseFloat(t.amount), 0),
      }));
  }, [transactions, activeTab, getGlobalIndex]);

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  };

  const formatAmount = (amount: string | number) => {
    const num = typeof amount === 'string' ? parseFloat(amount) : amount;
    return num.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  const handleNatureChange = (globalIndex: number, localIndex: number, nature: string) => {
    // Update local state immediately
    if (activeTab === 'in') {
      setLocalBankIn(prev => prev.map((t, i) =>
        i === localIndex ? { ...t, nature } : t
      ));
    } else {
      setLocalBankOut(prev => prev.map((t, i) =>
        i === localIndex ? { ...t, nature } : t
      ));
    }

    // Track pending changes
    setPendingChanges(prev => {
      const newMap = new Map(prev);
      const existing = newMap.get(globalIndex) || {};
      newMap.set(globalIndex, { ...existing, nature });
      return newMap;
    });

    setSaveStatus('idle');
  };

  const handleSaveChanges = async () => {
    if (pendingChanges.size === 0) return;

    setIsSaving(true);
    setSaveStatus('idle');

    try {
      const updates = Array.from(pendingChanges.entries()).map(([index, changes]) => ({
        index,
        ...changes,
      }));

      await updateTransactionsBulk(sessionId, updates);

      // Notify parent of updates
      if (onTransactionsUpdate) {
        onTransactionsUpdate(localBankIn, localBankOut);
      }

      setPendingChanges(new Map());
      setSaveStatus('saved');

      // Clear saved status after 3 seconds
      setTimeout(() => setSaveStatus('idle'), 3000);
    } catch (error) {
      console.error('Failed to save changes:', error);
      setSaveStatus('error');
    } finally {
      setIsSaving(false);
    }
  };

  // Find local index from transaction within currency group
  const findLocalIndex = (globalIndex: number): number => {
    if (activeTab === 'in') {
      return globalIndex;
    } else {
      return globalIndex - localBankIn.length;
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="border-b border-gray-200">
          <nav className="flex space-x-8">
            <button
              onClick={() => setActiveTab('in')}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'in'
                  ? 'border-green-500 text-green-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Bank In ({localBankIn.length})
            </button>
            <button
              onClick={() => setActiveTab('out')}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'out'
                  ? 'border-red-500 text-red-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Bank Out ({localBankOut.length})
            </button>
          </nav>
        </div>

        {/* Save Button */}
        <div className="flex items-center space-x-3">
          {saveStatus === 'saved' && (
            <span className="text-sm text-green-600">Changes saved!</span>
          )}
          {saveStatus === 'error' && (
            <span className="text-sm text-red-600">Failed to save</span>
          )}
          {pendingChanges.size > 0 && (
            <span className="text-sm text-gray-500">
              {pendingChanges.size} unsaved change{pendingChanges.size !== 1 ? 's' : ''}
            </span>
          )}
          <button
            onClick={handleSaveChanges}
            disabled={pendingChanges.size === 0 || isSaving}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              pendingChanges.size === 0
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            {isSaving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>

      <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
        {currencyGroups.length === 0 ? (
          <div className="py-8 text-center text-gray-500">
            No transactions found.
          </div>
        ) : (
          <div className="space-y-6">
            {currencyGroups.map((group) => (
              <div key={group.currency} className="border rounded-lg overflow-hidden">
                {/* Currency Section Header */}
                <div className={`px-4 py-3 flex items-center justify-between ${
                  activeTab === 'in' ? 'bg-green-50' : 'bg-red-50'
                }`}>
                  <div className="flex items-center space-x-3">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      activeTab === 'in'
                        ? 'bg-green-100 text-green-800'
                        : 'bg-red-100 text-red-800'
                    }`}>
                      {group.currency}
                    </span>
                    <span className="text-sm font-medium text-gray-700">
                      {group.currency} Saving Account
                    </span>
                    <span className="text-sm text-gray-500">
                      ({group.transactions.length} transaction{group.transactions.length !== 1 ? 's' : ''})
                    </span>
                  </div>
                  <div className={`text-sm font-semibold ${
                    activeTab === 'in' ? 'text-green-700' : 'text-red-700'
                  }`}>
                    Total: {formatAmount(group.total)} {group.currency}
                  </div>
                </div>

                {/* Transaction Table */}
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Date
                      </th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Amount
                      </th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        {group.currency !== 'HKD' ? 'Exchange Info' : ''}
                      </th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Description
                      </th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[180px]">
                        Nature
                      </th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Bank
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {group.transactions.map((transaction) => {
                      const localIndex = findLocalIndex(transaction.globalIndex);
                      return (
                        <tr key={transaction.globalIndex} className="hover:bg-gray-50">
                          <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-900">
                            {formatDate(transaction.date)}
                          </td>
                          <td
                            className={`px-3 py-2 whitespace-nowrap text-sm font-medium text-right ${
                              activeTab === 'in' ? 'text-green-600' : 'text-red-600'
                            }`}
                          >
                            {formatAmount(transaction.amount)}
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-500">
                            {group.currency !== 'HKD' && (
                              <span className="text-xs">
                                {group.currency}{transaction.amount}
                                {transaction.exchange_rate && ` @${transaction.exchange_rate}`}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-sm text-gray-600 max-w-xs truncate" title={transaction.description}>
                            {transaction.description}
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap">
                            <select
                              value={transaction.nature || ''}
                              onChange={(e) => handleNatureChange(transaction.globalIndex, localIndex, e.target.value)}
                              className={`text-sm border rounded-md px-2 py-1 w-full ${
                                pendingChanges.has(transaction.globalIndex)
                                  ? 'border-blue-400 bg-blue-50'
                                  : 'border-gray-300'
                              } focus:ring-2 focus:ring-blue-500 focus:border-blue-500`}
                            >
                              <option value="">-- Select --</option>
                              {natureOptions.map((option) => (
                                <option key={option} value={option}>
                                  {option}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-600">
                            {transaction.bank_name}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex justify-between items-center text-xs text-gray-500">
        <span>
          {currencyGroups.length} currency section{currencyGroups.length !== 1 ? 's' : ''}
        </span>
        <span>
          Showing {transactions.length} transactions
        </span>
      </div>
    </div>
  );
}

export default TransactionPreview;
