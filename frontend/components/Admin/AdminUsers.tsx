import React, { useEffect, useState } from 'react';
import { fetchAdminUsers } from '../../services/apiService';

interface AdminUser {
    id: number;
    username: string;
    is_admin: boolean;
    created_at: string;
}

const AdminUsers: React.FC = () => {
    const [users, setUsers] = useState<AdminUser[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const loadData = async () => {
            try {
                const data = await fetchAdminUsers();
                setUsers(data.data);
            } catch (err: any) {
                setError(err.message || 'Lỗi tải dữ liệu người dùng');
            } finally {
                setLoading(false);
            }
        };
        loadData();
    }, []);

    if (loading) return <div className="p-8 text-gray-500">Đang tải dữ liệu người dùng...</div>;
    if (error) return <div className="p-8 text-red-500">Lỗi: {error}</div>;

    return (
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
            <h2 className="text-xl font-bold text-gray-900 mb-6">Quản lý Người dùng</h2>

            <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                    <thead>
                        <tr className="bg-gray-50 border-b border-gray-200">
                            <th className="p-4 text-sm font-semibold text-gray-600">ID</th>
                            <th className="p-4 text-sm font-semibold text-gray-600">Tên đăng nhập</th>
                            <th className="p-4 text-sm font-semibold text-gray-600">Vai trò</th>
                            <th className="p-4 text-sm font-semibold text-gray-600">Ngày tạo</th>
                        </tr>
                    </thead>
                    <tbody>
                        {users.map((user) => (
                            <tr key={user.id} className="border-b border-gray-100 hover:bg-gray-50/50">
                                <td className="p-4 text-sm text-gray-600">#{user.id}</td>
                                <td className="p-4 text-sm font-medium text-gray-900">{user.username}</td>
                                <td className="p-4 text-sm">
                                    {user.is_admin ? (
                                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                                            Admin
                                        </span>
                                    ) : (
                                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                            Người dùng
                                        </span>
                                    )}
                                </td>
                                <td className="p-4 text-sm text-gray-500">
                                    {new Date(user.created_at).toLocaleString('vi-VN')}
                                </td>
                            </tr>
                        ))}
                        {users.length === 0 && (
                            <tr>
                                <td colSpan={4} className="p-4 text-sm text-gray-500 text-center">
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

export default AdminUsers;
