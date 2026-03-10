import React, { useEffect, useState } from 'react';
import { fetchAdminSessions } from '../../services/apiService';

interface AdminSession {
    id: string;
    title: string;
    mode: string;
    created_at: string;
    username: string;
}

const AdminSessions: React.FC = () => {
    const [sessions, setSessions] = useState<AdminSession[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const loadData = async () => {
            try {
                const data = await fetchAdminSessions();
                setSessions(data.data);
            } catch (err: any) {
                setError(err.message || 'Lỗi tải dữ liệu dữ liệu lịch sử');
            } finally {
                setLoading(false);
            }
        };
        loadData();
    }, []);

    if (loading) return <div className="p-8 text-gray-500">Đang tải lịch sử tra cứu...</div>;
    if (error) return <div className="p-8 text-red-500">Lỗi: {error}</div>;

    return (
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
            <h2 className="text-xl font-bold text-gray-900 mb-6">Lịch sử tra cứu người dùng</h2>

            <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                    <thead>
                        <tr className="bg-gray-50 border-b border-gray-200">
                            <th className="p-4 text-sm font-semibold text-gray-600">ID Phiên</th>
                            <th className="p-4 text-sm font-semibold text-gray-600">Người dùng</th>
                            <th className="p-4 text-sm font-semibold text-gray-600">Tiêu đề (Câu hỏi)</th>
                            <th className="p-4 text-sm font-semibold text-gray-600">Chế độ</th>
                            <th className="p-4 text-sm font-semibold text-gray-600">Ngày tạo</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sessions.map((session) => (
                            <tr key={session.id} className="border-b border-gray-100 hover:bg-gray-50/50">
                                <td className="p-4 text-sm text-gray-500 truncate max-w-[100px]" title={session.id}>{session.id}</td>
                                <td className="p-4 text-sm font-medium text-gray-900">{session.username}</td>
                                <td className="p-4 text-sm text-gray-700 truncate max-w-[200px]" title={session.title}>{session.title}</td>
                                <td className="p-4 text-sm">
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-blue-50 text-blue-700 uppercase">
                                        {session.mode}
                                    </span>
                                </td>
                                <td className="p-4 text-sm text-gray-500">
                                    {new Date(session.created_at).toLocaleString('vi-VN')}
                                </td>
                            </tr>
                        ))}
                        {sessions.length === 0 && (
                            <tr>
                                <td colSpan={5} className="p-4 text-sm text-gray-500 text-center">
                                    Không có dữ liệu
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default AdminSessions;
