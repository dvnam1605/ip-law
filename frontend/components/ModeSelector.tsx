import React from 'react';
import { ChatMode } from '../types';
import { BookOpen, Scale, Sparkles } from 'lucide-react';

interface ModeSelectorProps {
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
}

const modes: { key: ChatMode; label: string; icon: React.ReactNode }[] = [
  { key: 'smart', label: 'Tự động', icon: <Sparkles className="w-4 h-4" /> },
  { key: 'legal', label: 'Văn bản pháp luật', icon: <BookOpen className="w-4 h-4" /> },
  { key: 'verdict', label: 'Bản án', icon: <Scale className="w-4 h-4" /> },
];

const ModeSelector: React.FC<ModeSelectorProps> = ({ mode, onModeChange }) => {
  return (
    <div className="flex items-center bg-gray-100 dark:bg-gray-800 rounded-lg p-1 gap-1">
      {modes.map(({ key, label, icon }) => (
        <button
          key={key}
          onClick={() => onModeChange(key)}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${mode === key
              ? 'bg-white dark:bg-gray-700 text-black dark:text-white shadow-sm'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
            }`}
        >
          {icon}
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
};

export default ModeSelector;
