import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles } from 'lucide-react';

interface InputAreaProps {
  onSend: (text: string) => void;
  disabled: boolean;
}

const InputArea: React.FC<InputAreaProps> = ({ onSend, disabled }) => {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || input.trim().length < 2 || disabled) return;
    onSend(input.trim());
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  return (
    <div className="bg-white/80 dark:bg-gray-950/80 backdrop-blur-md border-t border-gray-100 dark:border-gray-800 px-4 py-6 md:px-8">
      <div className="max-w-3xl mx-auto relative">
        <form
          onSubmit={handleSubmit}
          className={`relative flex items-end gap-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-3xl px-4 py-3 shadow-sm hover:shadow-md hover:border-gray-300 dark:hover:border-gray-600 transition-all duration-200 focus-within:ring-2 focus-within:ring-gray-100 dark:focus-within:ring-gray-700 focus-within:border-gray-400 dark:focus-within:border-gray-500 ${disabled ? 'opacity-70 cursor-not-allowed' : ''}`}
        >
          <textarea
            ref={textareaRef}
            rows={1}
            disabled={disabled}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Nhập câu hỏi..."
            className="w-full bg-transparent border-0 focus:ring-0 resize-none max-h-32 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 py-2.5 scrollbar-hide font-light"
            style={{ minHeight: '24px' }}
          />
          <button
            type="submit"
            disabled={!input.trim() || disabled}
            className={`p-2.5 rounded-full flex-shrink-0 transition-all duration-200 ${!input.trim() || disabled
                ? 'bg-gray-100 dark:bg-gray-800 text-gray-300 dark:text-gray-600'
                : 'bg-black dark:bg-white text-white dark:text-black hover:bg-gray-800 dark:hover:bg-gray-200 hover:scale-105 active:scale-95'
              }`}
          >
            {disabled ? (
              <Sparkles className="w-5 h-5 animate-pulse" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </form>
        <div className="text-center mt-3">
          <p className="text-[10px] uppercase tracking-widest text-gray-300 dark:text-gray-600">
            IP Law AI
          </p>
        </div>
      </div>
    </div>
  );
};

export default InputArea;