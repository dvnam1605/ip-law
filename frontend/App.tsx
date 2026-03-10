import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import ChatApp from './ChatApp';
import AdminLayout from './components/Admin/AdminLayout';
import AdminDashboard from './components/Admin/AdminDashboard';
import AdminUsers from './components/Admin/AdminUsers';
import AdminSessions from './components/Admin/AdminSessions';
import AdminRoute from './components/AdminRoute';
import { getMe, setOnUnauthorized, clearToken } from './services/apiService';
import { User, ChatSession } from './types';
import LoginPage from './components/LoginPage';

const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [authChecking, setAuthChecking] = useState(true);

  useEffect(() => {
    setOnUnauthorized(() => {
      setUser(null);
    });

    const checkAuth = async () => {
      try {
        const userData = await getMe();
        if (userData) {
          setUser(userData);
        }
      } catch {
        // No valid token
      } finally {
        setAuthChecking(false);
      }
    };
    checkAuth();
  }, []);

  const handleLogin = async (userData: { id: number; username: string; is_admin?: boolean }, _token: string) => {
    const u: User = { id: userData.id, username: userData.username, is_admin: userData.is_admin, created_at: '' };
    setUser(u);
  };

  const handleLogout = () => {
    setUser(null);
  };

  if (authChecking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-3 border-black border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-400 text-sm">Đang kiểm tra phiên đăng nhập...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <Router>
      <Routes>
        {user.is_admin ? (
          <>
            <Route path="/admin" element={<AdminLayout username={user.username} onLogout={handleLogout} />}>
              <Route index element={<AdminDashboard />} />
              <Route path="users" element={<AdminUsers />} />
              <Route path="sessions" element={<AdminSessions />} />
              <Route path="settings" element={<div className="p-8">Tính năng cài đặt hệ thống (Đang phát triển)</div>} />
            </Route>
            <Route path="*" element={<Navigate to="/admin" replace />} />
          </>
        ) : (
          <>
            <Route
              path="/"
              element={<ChatApp user={user} onLogoutUser={handleLogout} onUserChange={setUser} />}
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </>
        )}
      </Routes>
    </Router>
  );
};

export default App;