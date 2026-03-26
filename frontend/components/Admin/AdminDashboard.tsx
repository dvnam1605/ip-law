import React, { useEffect, useState } from 'react';
import { fetchAdminStats } from '../../services/apiService';
import { Users, FileText, Scale, Activity, Link as LinkIcon } from 'lucide-react';
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    BarChart,
    Bar,
    Legend
} from 'recharts';

interface AdminStats {
    totals: {
        users: number;
        trademarks: number;
        visits: number;
        laws: number;
        precedents: number;
    };
    charts: {
        visits_over_time: { date: string; visits: number }[];
        users_over_time: { date: string; new_users: number }[];
    };
}

const StatCard = ({ title, value, icon: Icon, colorClass }: any) => (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700 flex items-center">
        <div className={`p-4 rounded-lg bg-${colorClass}-50 text-${colorClass}-600 dark:bg-${colorClass}-900/30 dark:text-${colorClass}-400 mr-5`}>
            <Icon className="w-8 h-8" />
        </div>
        <div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">{title}</p>
            <h3 className="text-3xl font-bold text-gray-900 dark:text-gray-100">{value}</h3>
        </div>
    </div>
);

const AdminDashboard: React.FC = () => {
    const [stats, setStats] = useState<AdminStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const loadStats = async () => {
            try {
                const data = await fetchAdminStats();
                setStats(data);
            } catch (err: any) {
                setError(err.message || 'Lỗi khi tải dữ liệu');
            } finally {
                setLoading(false);
            }
        };
        loadStats();
    }, []);

    if (loading) {
        return (
            <div className="flex h-full items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    if (error || !stats) {
        return (
            <div className="flex h-full items-center justify-center">
                <div className="text-red-500 bg-red-50 p-6 rounded-xl shadow-sm">
                    <h3 className="text-xl font-bold mb-2">Đã xảy ra lỗi</h3>
                    <p>{error}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="mb-8">
                <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Tổng quan hệ thống</h1>
                <p className="text-gray-500 dark:text-gray-400">Theo dõi các chỉ số quan trọng và hoạt động của người dùng.</p>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
                <StatCard title="Tổng người dùng" value={stats.totals.users} icon={Users} colorClass="blue" />
                <StatCard title="Tổng lượt tra cứu" value={stats.totals.visits} icon={Activity} colorClass="green" />
                <StatCard title="Nhãn hiệu đã tải" value={stats.totals.trademarks} icon={FileText} colorClass="purple" />
                <StatCard title="Văn bản Luật" value={stats.totals.laws} icon={Scale} colorClass="yellow" />
                <StatCard title="Án lệ" value={stats.totals.precedents} icon={LinkIcon} colorClass="red" />
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mt-10">

                {/* Lượt truy cập Chart */}
                <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700">
                    <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-6">Lượt tra cứu 7 ngày qua</h3>
                    <div className="h-80 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={stats.charts.visits_over_time} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                                <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: '#9CA3AF' }} dy={10} />
                                <YAxis axisLine={false} tickLine={false} tick={{ fill: '#9CA3AF' }} />
                                <Tooltip
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                                    cursor={{ stroke: '#E5E7EB', strokeWidth: 2 }}
                                />
                                <Legend iconType="circle" wrapperStyle={{ paddingTop: '20px' }} />
                                <Line
                                    type="monotone"
                                    name="Lượt tra cứu"
                                    dataKey="visits"
                                    stroke="#10B981"
                                    strokeWidth={3}
                                    dot={{ r: 4, strokeWidth: 2 }}
                                    activeDot={{ r: 6, stroke: '#10B981', strokeWidth: 2 }}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Người dùng mới Chart */}
                <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700">
                    <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-6">Người dùng mới 7 ngày qua</h3>
                    <div className="h-80 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={stats.charts.users_over_time} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                                <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: '#9CA3AF' }} dy={10} />
                                <YAxis axisLine={false} tickLine={false} tick={{ fill: '#9CA3AF' }} />
                                <Tooltip
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                                    cursor={{ fill: '#F3F4F6' }}
                                />
                                <Legend iconType="circle" wrapperStyle={{ paddingTop: '20px' }} />
                                <Bar
                                    name="Người dùng mới"
                                    dataKey="new_users"
                                    fill="#3B82F6"
                                    radius={[4, 4, 0, 0]}
                                    maxBarSize={50}
                                />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

            </div>
        </div>
    );
};

export default AdminDashboard;
