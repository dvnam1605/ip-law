import React, { useState } from 'react';
import { ArrowLeft, Search, Loader2 } from 'lucide-react';

const API_BASE = `http://${window.location.hostname}:1605`;

interface TrademarkResult {
  brand_name: string;
  owner_name: string;
  registration_number: string;
  nice_classes: string[];
  status: string;
  expiry_date: string;
  similarity_score: number;
  match_type: string;
  application_number: string;
  st13: string;
  feature: string;
}

interface Props {
  onBack: () => void;
  isDarkMode?: boolean;
}

const TrademarkSearchPage: React.FC<Props> = ({ onBack }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<TrademarkResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [totalFound, setTotalFound] = useState(0);
  const [timeMs, setTimeMs] = useState(0);
  const [searched, setSearched] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/api/trademark/search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ brand_name: query.trim(), limit: 50 }),
      });
      const data = await res.json();
      setResults(data.results || []);
      setTotalFound(data.total_found || 0);
      setTimeMs(data.processing_time_ms || 0);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-white dark:bg-gray-950 overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-800 px-6 py-4">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
            <ArrowLeft className="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </button>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">Tra cứu Nhãn hiệu</h1>
        </div>
      </div>

      {/* Search Bar */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-gray-100 dark:border-gray-800">
        <div className="max-w-2xl mx-auto flex gap-3">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Nhập tên nhãn hiệu cần tra cứu..."
            className="flex-1 px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={handleSearch}
            disabled={loading || !query.trim()}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white rounded-xl font-medium flex items-center gap-2 transition-colors"
          >
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Search className="w-5 h-5" />}
            Tra cứu
          </button>
        </div>
        {searched && !loading && (
          <div className="max-w-2xl mx-auto mt-2 text-sm text-gray-500">
            Tìm thấy {totalFound} kết quả ({(timeMs / 1000).toFixed(2)}s)
          </div>
        )}
      </div>

      {/* Results Table */}
      <div className="flex-1 overflow-auto px-6 py-4">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
          </div>
        ) : results.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="text-left py-3 px-3 font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap">#</th>
                  <th className="text-left py-3 px-3 font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap">Nhãn hiệu</th>
                  <th className="text-left py-3 px-3 font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap">Chủ sở hữu</th>
                  <th className="text-left py-3 px-3 font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap">Số đăng ký</th>
                  <th className="text-left py-3 px-3 font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap">Nhóm Nice</th>
                  <th className="text-left py-3 px-3 font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap">Trạng thái</th>
                  <th className="text-left py-3 px-3 font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap">Hết hạn</th>
                  <th className="text-left py-3 px-3 font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap">Mức giống</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-900/50 transition-colors">
                    <td className="py-3 px-3 text-gray-400">{i + 1}</td>
                    <td className="py-3 px-3 font-medium text-gray-900 dark:text-gray-100 max-w-[250px] truncate" title={r.brand_name}>{r.brand_name}</td>
                    <td className="py-3 px-3 text-gray-600 dark:text-gray-400 max-w-[200px] truncate" title={r.owner_name}>{r.owner_name || '—'}</td>
                    <td className="py-3 px-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{r.registration_number || '—'}</td>
                    <td className="py-3 px-3 text-gray-600 dark:text-gray-400">{r.nice_classes?.join(', ') || '—'}</td>
                    <td className="py-3 px-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        r.status === 'Registered' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                        r.status === 'Expired' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                        'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                      }`}>
                        {r.status || '—'}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-gray-600 dark:text-gray-400 whitespace-nowrap">{r.expiry_date || '—'}</td>
                    <td className="py-3 px-3">
                      <span className={`font-medium ${r.similarity_score >= 0.9 ? 'text-red-600' : r.similarity_score >= 0.7 ? 'text-yellow-600' : 'text-green-600'}`}>
                        {(r.similarity_score * 100).toFixed(0)}%
                      </span>
                      <span className="text-gray-400 text-xs ml-1">({r.match_type})</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : searched ? (
          <div className="text-center py-20 text-gray-400">
            Không tìm thấy nhãn hiệu nào phù hợp
          </div>
        ) : (
          <div className="text-center py-20 text-gray-300">
            <Search className="w-16 h-16 mx-auto mb-4 opacity-30" />
            <p className="text-lg">Nhập tên nhãn hiệu để bắt đầu tra cứu</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default TrademarkSearchPage;
