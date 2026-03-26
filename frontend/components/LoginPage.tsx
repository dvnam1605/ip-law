import React, { useState } from 'react';
import { Bot, ArrowRight, UserPlus, LogIn, Eye, EyeOff } from 'lucide-react';

interface LoginPageProps {
  onLogin: (user: { id: number; username: string }, token: string) => void;
  error?: string;
}

const LoginPage: React.FC<LoginPageProps> = ({ onLogin, error: externalError }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isRegister, setIsRegister] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;

    // Validate confirm password on register
    if (isRegister && password !== confirmPassword) {
      setError('Mật khẩu xác nhận không khớp');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const { registerUser, loginUser } = await import('../services/apiService');
      if (isRegister) {
        const result = await registerUser(username.trim(), password, confirmPassword);
        onLogin(result.user, result.access_token);
      } else {
        const result = await loginUser(username.trim(), password);
        onLogin(result.user, result.access_token);
      }
    } catch (err: any) {
      setError(err.message || 'Đã xảy ra lỗi');
    } finally {
      setLoading(false);
    }
  };

  const displayError = error || externalError;

  return (
    <div className="min-h-screen flex items-center justify-center bg-white px-4">
      <div className="max-w-md w-full text-center">
        <div className="w-20 h-20 bg-black rounded-full flex items-center justify-center mx-auto mb-8 shadow-2xl">
          <Bot className="w-10 h-10 text-white" />
        </div>

        <h1 className="text-3xl font-bold text-gray-900 mb-3 tracking-tight">AI Assistant</h1>
        <p className="text-gray-500 mb-10 text-lg font-light">
          {isRegister ? 'Tạo tài khoản mới' : 'Đăng nhập để bắt đầu trải nghiệm'}
        </p>

        {displayError && (
          <div className="mb-6 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-red-600 text-sm">
            {displayError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="text-left">
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-4 bg-gray-50 rounded-xl border-2 border-transparent focus:border-black focus:bg-white outline-none transition-all text-gray-900 placeholder-gray-400 font-medium"
              placeholder="Tên đăng nhập"
              required
              autoComplete="username"
            />
          </div>

          <div className="text-left relative">
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-4 pr-12 bg-gray-50 rounded-xl border-2 border-transparent focus:border-black focus:bg-white outline-none transition-all text-gray-900 placeholder-gray-400 font-medium"
              placeholder="Mật khẩu"
              required
              minLength={6}
              autoComplete={isRegister ? 'new-password' : 'current-password'}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 transition-colors"
            >
              {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
            </button>
          </div>

          {isRegister && (
            <div className="text-left relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className={`w-full px-4 py-4 pr-12 bg-gray-50 rounded-xl border-2 outline-none transition-all text-gray-900 placeholder-gray-400 font-medium ${confirmPassword && confirmPassword !== password
                    ? 'border-red-400 focus:border-red-500'
                    : 'border-transparent focus:border-black focus:bg-white'
                  }`}
                placeholder="Xác nhận mật khẩu"
                required
                minLength={6}
                autoComplete="new-password"
              />
              {confirmPassword && confirmPassword !== password && (
                <p className="mt-1 text-xs text-red-500">Mật khẩu không khớp</p>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || (isRegister && password !== confirmPassword)}
            className="w-full bg-black hover:bg-gray-800 disabled:bg-gray-400 text-white font-medium py-4 rounded-xl transition-all flex items-center justify-center gap-2 group shadow-lg shadow-gray-200"
          >
            {loading ? (
              <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <>
                {isRegister ? <UserPlus className="w-5 h-5" /> : <LogIn className="w-5 h-5" />}
                <span>{isRegister ? 'Đăng ký' : 'Đăng nhập'}</span>
                <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </>
            )}
          </button>
        </form>

        <button
          onClick={() => { setIsRegister(!isRegister); setError(''); setConfirmPassword(''); }}
          className="mt-6 text-sm text-gray-500 hover:text-black transition-colors"
        >
          {isRegister ? 'Đã có tài khoản? Đăng nhập' : 'Chưa có tài khoản? Đăng ký'}
        </button>

        <div className="mt-12 pt-8 border-t border-gray-100">
          <p className="text-xs text-gray-400 font-mono">
            CONNECTION: LOCALHOST:1605
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;