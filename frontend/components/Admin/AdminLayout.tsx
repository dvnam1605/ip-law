import React from 'react';
import { useNavigate, Outlet, useLocation } from 'react-router-dom';
import { LogOut, LayoutDashboard, Settings, Users, MessageSquare } from 'lucide-react';
import { logoutUser } from '../../services/apiService';

interface AdminLayoutProps {
    onLogout: () => void;
    username: string;
}

const AdminLayout: React.FC<AdminLayoutProps> = ({ onLogout, username }) => {
    const navigate = useNavigate();
    const location = useLocation();

    const handleLogout = async () => {
        await logoutUser();
        onLogout();
        navigate('/');
    };

    const navItems = [
        { name: 'Tổng quan', path: '/admin', icon: LayoutDashboard },
        { name: 'Quản lý Users', path: '/admin/users', icon: Users },
        { name: 'Quản lý Hội thoại', path: '/admin/sessions', icon: MessageSquare },
        { name: 'Cài đặt hệ thống', path: '/admin/settings', icon: Settings },
    ];

    return (
        <div className="flex h-screen bg-gray-50 flex-col md:flex-row">
            {/* Sidebar Admin */}
            <aside className="w-full md:w-64 bg-gray-900 text-white flex flex-col shrink-0">
                <div className="p-6">
                    <h2 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                        <span className="bg-blue-600 p-1.5 rounded-lg">
                            <LayoutDashboard size={20} />
                        </span>
                        Admin Portal
                    </h2>
                </div>

                <nav className="flex-1 px-4 space-y-2 mt-4">
                    {navItems.map((item) => {
                        const isActive = location.pathname === item.path;
                        const Icon = item.icon;
                        return (
                            <button
                                key={item.path}
                                onClick={() => navigate(item.path)}
                                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-colors ${isActive
                                    ? 'bg-blue-600/10 text-blue-400 font-medium'
                                    : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                                    }`}
                            >
                                <Icon size={20} />
                                <span>{item.name}</span>
                            </button>
                        )
                    })}
                </nav>

                <div className="p-4 border-t border-gray-800">
                    <div className="flex items-center gap-3 px-4 py-3 mb-2 rounded-xl bg-gray-800/50">
                        <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center font-bold text-white uppercase">
                            {username[0]}
                        </div>
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-white truncate">{username}</p>
                            <p className="text-xs text-gray-400">Quản trị viên</p>
                        </div>
                    </div>
                    <button
                        onClick={handleLogout}
                        className="w-full flex items-center justify-center gap-2 px-4 py-2 text-sm text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded-lg transition-colors mt-2"
                    >
                        <LogOut size={18} />
                        <span>Đăng xuất</span>
                    </button>
                </div>
            </aside>

            {/* Main Content Area */}
            <main className="flex-1 overflow-auto bg-gray-50 dark:bg-gray-900 p-8">
                <div className="max-w-7xl mx-auto">
                    <Outlet />
                </div>
            </main>
        </div>
    );
};

export default AdminLayout;
