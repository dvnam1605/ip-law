import React, { useState, useRef, useEffect } from 'react';
import { ChatSession } from '../types';
import { 
  MessageSquarePlus, 
  MessageSquare, 
  LogOut, 
  PanelLeftClose, 
  MoreHorizontal, 
  Pencil, 
  Trash2, 
  Share2,
  Check,
  X
} from 'lucide-react';

interface SidebarProps {
  sessions: ChatSession[];
  currentSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onRenameSession: (id: string, newTitle: string) => void;
  onDeleteSession: (id: string) => void;
  onShareSession: (id: string) => void;
  onLogout: () => void;
  isMobileOpen: boolean;
  username: string;
  isDesktopOpen: boolean;
  toggleDesktopSidebar: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ 
  sessions, 
  currentSessionId, 
  onSelectSession, 
  onNewChat, 
  onRenameSession,
  onDeleteSession,
  onShareSession,
  onLogout,
  isMobileOpen,
  username,
  isDesktopOpen,
  toggleDesktopSidebar
}) => {
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  
  const editInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setActiveMenuId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Focus input when editing starts
  useEffect(() => {
    if (editingSessionId && editInputRef.current) {
      editInputRef.current.focus();
    }
  }, [editingSessionId]);

  const handleStartRename = (session: ChatSession, e: React.MouseEvent) => {
    e.stopPropagation();
    setActiveMenuId(null);
    setEditingSessionId(session.id);
    setEditTitle(session.title);
  };

  const handleSaveRename = () => {
    if (editingSessionId && editTitle.trim()) {
      onRenameSession(editingSessionId, editTitle.trim());
      setEditingSessionId(null);
    }
  };

  const handleCancelRename = () => {
    setEditingSessionId(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSaveRename();
    if (e.key === 'Escape') handleCancelRename();
  };

  return (
    <div className={`
      fixed inset-y-0 left-0 z-30 bg-black text-white transform transition-all duration-300 ease-in-out flex flex-col border-r border-gray-900
      ${isMobileOpen ? 'translate-x-0 w-[280px]' : '-translate-x-full w-[280px]'}
      md:relative md:translate-x-0 ${isDesktopOpen ? 'md:w-[280px]' : 'md:w-0 md:overflow-hidden md:border-r-0'}
    `}>
      {/* Header / New Chat */}
      <div className="p-4 flex items-center justify-between gap-2">
        <button
          onClick={onNewChat}
          className="flex-1 flex items-center gap-3 px-4 py-3 rounded-xl bg-white text-black hover:bg-gray-200 transition-colors text-sm font-medium whitespace-nowrap overflow-hidden"
        >
          <MessageSquarePlus className="w-4 h-4 flex-shrink-0" />
          <span>Đoạn chat mới</span>
        </button>
        
        {/* Toggle button visible only inside sidebar on Desktop */}
        <button 
            onClick={toggleDesktopSidebar}
            className="hidden md:flex p-3 text-gray-400 hover:text-white rounded-xl hover:bg-gray-900 transition-colors"
            title="Ẩn thanh bên"
        >
            <PanelLeftClose className="w-5 h-5" />
        </button>
      </div>

      {/* History List */}
      <div className="flex-1 overflow-y-auto dark-scrollbar px-3 py-2 pb-20">
        <div className="text-xs font-bold text-gray-500 mb-3 px-3 uppercase tracking-wider">Lịch sử</div>
        <div className="flex flex-col gap-1">
          {sessions.length === 0 ? (
            <div className="px-3 py-2 text-sm text-gray-500 italic font-light">Chưa có lịch sử chat</div>
          ) : (
            sessions.slice().reverse().map((session) => (
              <div 
                key={session.id} 
                className={`group relative flex items-center rounded-lg transition-all ${currentSessionId === session.id ? 'bg-gray-900' : 'hover:bg-gray-900'}`}
              >
                {/* Editing Mode */}
                {editingSessionId === session.id ? (
                   <div className="flex items-center w-full px-2 py-2 gap-1">
                     <input
                        ref={editInputRef}
                        type="text"
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={handleKeyDown}
                        className="flex-1 bg-gray-800 text-white text-sm px-2 py-1 rounded outline-none border border-gray-600 focus:border-white"
                     />
                     <button onClick={handleSaveRename} className="p-1 text-green-400 hover:bg-gray-800 rounded">
                        <Check size={14} />
                     </button>
                     <button onClick={handleCancelRename} className="p-1 text-red-400 hover:bg-gray-800 rounded">
                        <X size={14} />
                     </button>
                   </div>
                ) : (
                  /* Display Mode */
                  <>
                    <button
                        onClick={() => onSelectSession(session.id)}
                        className="flex items-center gap-3 px-3 py-3 w-full text-left overflow-hidden"
                    >
                        <MessageSquare className={`w-4 h-4 flex-shrink-0 ${currentSessionId === session.id ? 'text-white' : 'text-gray-600 group-hover:text-gray-400'}`} />
                        <span className={`truncate flex-1 text-sm ${currentSessionId === session.id ? 'text-white font-medium' : 'text-gray-400 group-hover:text-gray-200'}`}>
                            {session.title}
                        </span>
                    </button>

                    {/* Menu Trigger Button - Visible on hover or if menu is active */}
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            setActiveMenuId(activeMenuId === session.id ? null : session.id);
                        }}
                        className={`absolute right-2 p-1.5 rounded-md text-gray-400 hover:text-white hover:bg-gray-800 transition-opacity ${activeMenuId === session.id ? 'opacity-100 bg-gray-800 text-white' : 'opacity-0 group-hover:opacity-100'}`}
                    >
                        <MoreHorizontal size={16} />
                    </button>

                    {/* Context Menu (Dropdown) */}
                    {activeMenuId === session.id && (
                        <div 
                            ref={menuRef}
                            className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-xl z-50 overflow-hidden py-1 animate-in fade-in zoom-in-95 duration-100"
                            style={{ top: '80%', right: '10px' }} 
                        >
                            <button 
                                onClick={(e) => handleStartRename(session, e)}
                                className="w-full text-left px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2"
                            >
                                <Pencil size={14} /> Đổi tên
                            </button>
                            <button 
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onShareSession(session.id);
                                    setActiveMenuId(null);
                                }}
                                className="w-full text-left px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-100 flex items-center gap-2"
                            >
                                <Share2 size={14} /> Chia sẻ
                            </button>
                            <div className="h-px bg-gray-100 my-1"></div>
                            <button 
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onDeleteSession(session.id);
                                    setActiveMenuId(null);
                                }}
                                className="w-full text-left px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
                            >
                                <Trash2 size={14} /> Xóa
                            </button>
                        </div>
                    )}
                  </>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* User Footer */}
      <div className="p-4 border-t border-gray-900 bg-black">
        <div className="flex items-center justify-between px-3 py-2 rounded-xl hover:bg-gray-900 cursor-pointer group transition-colors">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="w-8 h-8 rounded-full bg-white text-black flex items-center justify-center font-bold text-xs flex-shrink-0">
              {username.charAt(0).toUpperCase()}
            </div>
            <div className="text-sm font-medium truncate">{username}</div>
          </div>
          <button 
            onClick={onLogout}
            className="text-gray-500 hover:text-white p-1 rounded transition-colors"
            title="Đăng xuất"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;