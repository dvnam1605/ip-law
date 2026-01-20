import React, { useState } from 'react';
import { Bot, ArrowRight } from 'lucide-react';

interface LoginPageProps {
  onLogin: (username: string) => void;
}

const LoginPage: React.FC<LoginPageProps> = ({ onLogin }) => {
  const [username, setUsername] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (username.trim()) {
      onLogin(username);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-white px-4">
      <div className="max-w-md w-full text-center">
        <div className="w-20 h-20 bg-black rounded-full flex items-center justify-center mx-auto mb-8 shadow-2xl">
          <Bot className="w-10 h-10 text-white" />
        </div>
        
        <h1 className="text-3xl font-bold text-gray-900 mb-3 tracking-tight">AI Assistant</h1>
        <p className="text-gray-500 mb-10 text-lg font-light">Đăng nhập để bắt đầu trải nghiệm</p>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="text-left group">
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-4 bg-gray-50 rounded-xl border-2 border-transparent focus:border-black focus:bg-white outline-none transition-all text-gray-900 placeholder-gray-400 font-medium"
              placeholder="Tên của bạn"
              required
            />
          </div>

          <button
            type="submit"
            className="w-full bg-black hover:bg-gray-800 text-white font-medium py-4 rounded-xl transition-all flex items-center justify-center gap-2 group shadow-lg shadow-gray-200"
          >
            <span>Tiếp tục</span>
            <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
          </button>
        </form>
        
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