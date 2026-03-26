import React, { useState } from 'react';
import { ArrowLeft, User, Lock, CheckCircle, AlertCircle } from 'lucide-react';
import { changeUsername, changePassword } from '../services/apiService';

interface SettingsPageProps {
    username: string;
    onBack: () => void;
    onUsernameChanged: (newUsername: string) => void;
    isDarkMode?: boolean;
}

const SettingsPage: React.FC<SettingsPageProps> = ({ username, onBack, onUsernameChanged }) => {
    // Username form
    const [newUsername, setNewUsername] = useState(username);
    const [usernameLoading, setUsernameLoading] = useState(false);
    const [usernameMsg, setUsernameMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

    // Password form
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [passwordLoading, setPasswordLoading] = useState(false);
    const [passwordMsg, setPasswordMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

    const handleChangeUsername = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!newUsername.trim() || newUsername === username) return;
        setUsernameLoading(true);
        setUsernameMsg(null);
        try {
            const result = await changeUsername(newUsername.trim());
            setUsernameMsg({ type: 'success', text: 'Đổi tên đăng nhập thành công!' });
            onUsernameChanged(result.username);
        } catch (err: any) {
            setUsernameMsg({ type: 'error', text: err.message || 'Có lỗi xảy ra' });
        } finally {
            setUsernameLoading(false);
        }
    };

    const handleChangePassword = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!currentPassword || !newPassword || !confirmPassword) return;
        if (newPassword !== confirmPassword) {
            setPasswordMsg({ type: 'error', text: 'Mật khẩu xác nhận không khớp' });
            return;
        }
        if (newPassword.length < 6) {
            setPasswordMsg({ type: 'error', text: 'Mật khẩu mới phải có ít nhất 6 ký tự' });
            return;
        }
        setPasswordLoading(true);
        setPasswordMsg(null);
        try {
            await changePassword(currentPassword, newPassword, confirmPassword);
            setPasswordMsg({ type: 'success', text: 'Đổi mật khẩu thành công!' });
            setCurrentPassword('');
            setNewPassword('');
            setConfirmPassword('');
        } catch (err: any) {
            setPasswordMsg({ type: 'error', text: err.message || 'Có lỗi xảy ra' });
        } finally {
            setPasswordLoading(false);
        }
    };

    return (
        <div className="flex-1 flex flex-col h-full bg-gray-50 dark:bg-gray-950 overflow-y-auto">
            {/* Header */}
            <div className="sticky top-0 z-10 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 py-4">
                <div className="max-w-2xl mx-auto flex items-center gap-4">
                    <button
                        onClick={onBack}
                        className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                        title="Quay lại"
                    >
                        <ArrowLeft className="w-5 h-5" />
                    </button>
                    <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Cài đặt</h1>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-2xl mx-auto w-full px-6 py-8 space-y-8">

                {/* Change Username */}
                <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-800 overflow-hidden">
                    <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/50">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
                                <User className="w-5 h-5" />
                            </div>
                            <div>
                                <h2 className="font-semibold text-gray-900 dark:text-gray-100">Đổi tên đăng nhập</h2>
                                <p className="text-sm text-gray-500 dark:text-gray-400">Tên đăng nhập hiện tại: <strong>{username}</strong></p>
                            </div>
                        </div>
                    </div>
                    <form onSubmit={handleChangeUsername} className="p-6 space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Tên đăng nhập mới
                            </label>
                            <input
                                type="text"
                                value={newUsername}
                                onChange={(e) => setNewUsername(e.target.value)}
                                className="w-full px-4 py-3 border border-gray-300 dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                                placeholder="Nhập tên đăng nhập mới"
                                minLength={3}
                                maxLength={100}
                            />
                        </div>
                        {usernameMsg && (
                            <div className={`flex items-center gap-2 text-sm px-4 py-3 rounded-xl ${usernameMsg.type === 'success'
                                    ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800'
                                    : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800'
                                }`}>
                                {usernameMsg.type === 'success' ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                                {usernameMsg.text}
                            </div>
                        )}
                        <button
                            type="submit"
                            disabled={usernameLoading || !newUsername.trim() || newUsername === username}
                            className="w-full py-3 px-4 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:cursor-not-allowed transition-colors"
                        >
                            {usernameLoading ? 'Đang cập nhật...' : 'Lưu thay đổi'}
                        </button>
                    </form>
                </div>

                {/* Change Password */}
                <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-800 overflow-hidden">
                    <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/50">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400">
                                <Lock className="w-5 h-5" />
                            </div>
                            <div>
                                <h2 className="font-semibold text-gray-900 dark:text-gray-100">Đổi mật khẩu</h2>
                                <p className="text-sm text-gray-500 dark:text-gray-400">Để bảo mật, hãy dùng mật khẩu mạnh</p>
                            </div>
                        </div>
                    </div>
                    <form onSubmit={handleChangePassword} className="p-6 space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Mật khẩu hiện tại
                            </label>
                            <input
                                type="password"
                                value={currentPassword}
                                onChange={(e) => setCurrentPassword(e.target.value)}
                                className="w-full px-4 py-3 border border-gray-300 dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-amber-500 focus:border-amber-500 outline-none transition-all text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                                placeholder="Nhập mật khẩu hiện tại"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Mật khẩu mới
                            </label>
                            <input
                                type="password"
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                className="w-full px-4 py-3 border border-gray-300 dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-amber-500 focus:border-amber-500 outline-none transition-all text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                                placeholder="Nhập mật khẩu mới (ít nhất 6 ký tự)"
                                minLength={6}
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Xác nhận mật khẩu mới
                            </label>
                            <input
                                type="password"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                className="w-full px-4 py-3 border border-gray-300 dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-amber-500 focus:border-amber-500 outline-none transition-all text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
                                placeholder="Nhập lại mật khẩu mới"
                                minLength={6}
                            />
                        </div>
                        {passwordMsg && (
                            <div className={`flex items-center gap-2 text-sm px-4 py-3 rounded-xl ${passwordMsg.type === 'success'
                                    ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800'
                                    : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800'
                                }`}>
                                {passwordMsg.type === 'success' ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                                {passwordMsg.text}
                            </div>
                        )}
                        <button
                            type="submit"
                            disabled={passwordLoading || !currentPassword || !newPassword || !confirmPassword}
                            className="w-full py-3 px-4 bg-amber-600 text-white rounded-xl font-medium hover:bg-amber-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:cursor-not-allowed transition-colors"
                        >
                            {passwordLoading ? 'Đang cập nhật...' : 'Đổi mật khẩu'}
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
};

export default SettingsPage;
