import React, { useState, useRef, useEffect } from 'react';
import { Message, ChatSession, User, ChatMode } from './types';
import {
  sendQueryToBackendStream,
  getMe,
  clearToken,
  logoutUser,
  setOnUnauthorized,
  fetchSessions,
  createSessionApi,
  renameSessionApi,
  deleteSessionApi,
  fetchMessages,
  saveMessage,
} from './services/apiService';
import MessageBubble from './components/MessageBubble';
import InputArea from './components/InputArea';
import TypingIndicator from './components/TypingIndicator';
import Sidebar from './components/Sidebar';
import LoginPage from './components/LoginPage';
import SettingsPage from './components/SettingsPage';
import TrademarkSearchPage from './components/TrademarkSearchPage';
import ModeSelector from './components/ModeSelector';
import { Bot, Menu, PanelLeftOpen } from 'lucide-react';

const App: React.FC = () => {
  // --- State ---
  const [user, setUser] = useState<User | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [chatMode, setChatMode] = useState<ChatMode>('smart');
  const [authChecking, setAuthChecking] = useState(true);

  // Sidebar State
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isDesktopSidebarOpen, setIsDesktopSidebarOpen] = useState(true);
  const [currentView, setCurrentView] = useState<'chat' | 'settings' | 'trademark-search'>('chat');

  // Theme state - persisted to localStorage
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const saved = localStorage.getItem('theme');
    return saved === 'dark';
  });

  // Apply dark class to <html> element
  useEffect(() => {
    const root = document.documentElement;
    if (isDarkMode) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    localStorage.setItem('theme', isDarkMode ? 'dark' : 'light');
  }, [isDarkMode]);

  const toggleTheme = () => setIsDarkMode(prev => !prev);

  // --- Refs ---
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // --- Effects ---
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [sessions, currentSessionId, isLoading]);

  // Auto-login on mount if token exists
  useEffect(() => {
    // Register global 401 handler
    setOnUnauthorized(() => {
      setUser(null);
      setSessions([]);
      setCurrentSessionId(null);
    });

    const checkAuth = async () => {
      try {
        const userData = await getMe();
        if (userData) {
          setUser(userData);
          await loadSessions(userData);
        }
      } catch {
        // No valid token
      } finally {
        setAuthChecking(false);
      }
    };
    checkAuth();
  }, []);

  // --- Data loading ---

  const loadSessions = async (_user?: User | null) => {
    try {
      const apiSessions = await fetchSessions();
      const localSessions: ChatSession[] = apiSessions.map(s => ({
        id: s.id,
        title: s.title,
        messages: [],
        createdAt: new Date(s.created_at),
        mode: s.mode as ChatMode,
      }));
      setSessions(localSessions);
      if (localSessions.length > 0) {
        const lastSession = localSessions[localSessions.length - 1];
        setCurrentSessionId(lastSession.id);
        setChatMode(lastSession.mode || 'smart');
        await loadMessages(lastSession.id, localSessions);
      } else {
        // Auto-create first session for new users
        await createNewSession();
      }
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  };

  const loadMessages = async (sessionId: string, currentSessions?: ChatSession[]) => {
    try {
      const apiMessages = await fetchMessages(sessionId);
      const msgs: Message[] = apiMessages.map(m => ({
        id: m.id,
        role: m.role as 'user' | 'assistant',
        content: m.content,
        timestamp: new Date(m.created_at),
        routeType: m.route_type || undefined,
      }));

      const updateFn = (prev: ChatSession[]) =>
        prev.map(s => s.id === sessionId ? { ...s, messages: msgs } : s);

      if (currentSessions) {
        setSessions(updateFn(currentSessions));
      } else {
        setSessions(prev => updateFn(prev));
      }
    } catch (err) {
      console.error('Failed to load messages:', err);
    }
  };

  // --- Logic ---

  const handleLogin = async (userData: { id: number; username: string }, _token: string) => {
    const u: User = { id: userData.id, username: userData.username, created_at: '' };
    setUser(u);
    await loadSessions(u);
  };

  const handleLogout = async () => {
    await logoutUser();
    setUser(null);
    setSessions([]);
    setCurrentSessionId(null);
  };

  const createNewSession = async (overrideMode?: ChatMode) => {
    const mode = overrideMode || chatMode;

    // If there's already an empty "Đoạn chat mới" with same mode, just switch to it
    const existingEmpty = sessions.find(s =>
      s.title === 'Đoạn chat mới' &&
      s.mode === mode &&
      s.messages.length <= 1
    );
    if (existingEmpty) {
      setCurrentSessionId(existingEmpty.id);
      setChatMode(mode);
      setIsMobileSidebarOpen(false);
      setCurrentView('chat');
      return;
    }

    try {
      const apiSession = await createSessionApi('Đoạn chat mới', mode);
      console.log('[createNewSession] API returned:', apiSession);
      const welcomeMessages: Record<ChatMode, string> = {
        smart: 'Xin chào! Hãy hỏi bất kỳ câu hỏi nào về Sở hữu trí tuệ — tôi sẽ tự động tìm nguồn phù hợp nhất (luật, bản án, hoặc cả hai).',
        verdict: 'Xin chào! Tôi có thể phân tích tình huống pháp lý dựa trên các bản án thực tế về Sở hữu trí tuệ. Hãy mô tả tình huống của bạn!',
        legal: 'Xin chào! Tôi có thể giúp gì cho bạn về các quy định pháp luật?',
        trademark: 'Xin chào! Tôi có thể tra cứu nhãn hiệu đã đăng ký và phân tích xung đột. Hãy nhập tên nhãn hiệu bạn muốn kiểm tra!',
      };

      // Save welcome message to backend
      await saveMessage(apiSession.id, 'assistant', welcomeMessages[mode]);

      const newSession: ChatSession = {
        id: apiSession.id,
        title: 'Đoạn chat mới',
        messages: [{
          id: 'welcome-' + apiSession.id,
          role: 'assistant',
          content: welcomeMessages[mode],
          timestamp: new Date()
        }],
        createdAt: new Date(apiSession.created_at),
        mode: mode
      };
      setSessions(prev => [...prev, newSession]);
      setCurrentSessionId(newSession.id);
      setIsMobileSidebarOpen(false);
      setCurrentView('chat');
    } catch (err) {
      console.error('Failed to create session:', err);
    }
  };

  const handleSelectSession = async (id: string) => {
    setCurrentSessionId(id);
    const session = sessions.find(s => s.id === id);
    if (session?.mode) {
      setChatMode(session.mode);
    }
    setIsMobileSidebarOpen(false);
    setCurrentView('chat');

    // Load messages if not already loaded
    if (session && session.messages.length === 0) {
      await loadMessages(id);
    }
  };

  const handleRenameSession = async (id: string, newTitle: string) => {
    try {
      await renameSessionApi(id, newTitle);
      setSessions(prev => prev.map(session =>
        session.id === id ? { ...session, title: newTitle } : session
      ));
    } catch (err) {
      console.error('Failed to rename session:', err);
    }
  };

  const handleDeleteSession = async (id: string) => {
    if (!window.confirm('Bạn có chắc chắn muốn xóa cuộc trò chuyện này không?')) return;

    try {
      await deleteSessionApi(id);
      const updatedSessions = sessions.filter(s => s.id !== id);

      if (updatedSessions.length === 0) {
        setSessions([]);
        setCurrentSessionId(null);
        await createNewSession();
        return;
      } else {
        setSessions(updatedSessions);
        if (currentSessionId === id) {
          setCurrentSessionId(updatedSessions[updatedSessions.length - 1].id);
        }
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  };

  const handleShareSession = (id: string) => {
    const shareUrl = `${window.location.origin}/chat/${id}`;
    window.prompt('Sao chép liên kết dưới đây để chia sẻ:', shareUrl);
  };

  const updateCurrentSessionMessages = (newMessage: Message) => {
    setSessions(prevSessions => prevSessions.map(session => {
      if (session.id === currentSessionId) {
        let newTitle = session.title;
        if (session.title === 'Đoạn chat mới' && newMessage.role === 'user') {
          newTitle = newMessage.content.slice(0, 30) + (newMessage.content.length > 30 ? '...' : '');
        }

        return {
          ...session,
          title: newTitle,
          messages: [...session.messages, newMessage]
        };
      }
      return session;
    }));
  };

  const updateMessageContent = (messageId: string, content: string) => {
    setSessions(prevSessions => prevSessions.map(session => {
      if (session.id === currentSessionId) {
        return {
          ...session,
          messages: session.messages.map(msg =>
            msg.id === messageId ? { ...msg, content } : msg
          )
        };
      }
      return session;
    }));
  };

  const updateMessageRouteType = (messageId: string, routeType: string) => {
    setSessions(prevSessions => prevSessions.map(session => {
      if (session.id === currentSessionId) {
        return {
          ...session,
          messages: session.messages.map(msg =>
            msg.id === messageId ? { ...msg, routeType } : msg
          )
        };
      }
      return session;
    }));
  };

  const handleSendMessage = async (text: string) => {
    if (!currentSessionId) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    };

    updateCurrentSessionMessages(userMessage);
    setIsLoading(true);

    // Save user message to DB
    try {
      await saveMessage(currentSessionId, 'user', text);
    } catch (err) {
      console.error('Failed to save user message:', err);
    }

    // Auto-rename on first user message
    const currentSess = sessions.find(s => s.id === currentSessionId);
    if (currentSess && currentSess.title === 'Đoạn chat mới') {
      const newTitle = text.slice(0, 30) + (text.length > 30 ? '...' : '');
      renameSessionApi(currentSessionId, newTitle).catch(console.error);
    }

    const botMessageId = (Date.now() + 1).toString();
    const botMessage: Message = {
      id: botMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
    };
    updateCurrentSessionMessages(botMessage);

    let botRouteType: string | undefined;

    try {
      const sessionMode = currentSess?.mode || chatMode;
      await sendQueryToBackendStream(
        text,
        (_chunk, fullText) => {
          updateMessageContent(botMessageId, fullText);
        },
        (fullText) => {
          setIsLoading(false);
          // Save bot reply to DB
          if (currentSessionId && fullText) {
            saveMessage(currentSessionId, 'assistant', fullText, botRouteType).catch(console.error);
          }
        },
        (error) => {
          const errMsg = 'Xin lỗi, tôi không thể kết nối đến máy chủ (Port 1605).';
          updateMessageContent(botMessageId, errMsg);
          console.error('Stream error:', error);
          setIsLoading(false);
          if (currentSessionId) {
            saveMessage(currentSessionId, 'assistant', errMsg).catch(console.error);
          }
        },
        sessionMode,
        (route) => {
          botRouteType = route;
          updateMessageRouteType(botMessageId, route);
        },
        currentSessionId || undefined,
      );
    } catch (error) {
      // handled by onError callback
    } finally {
      setIsLoading(false);
    }
  };

  // --- Derived State ---
  const currentSession = sessions.find(s => s.id === currentSessionId);
  const currentMessages = currentSession ? currentSession.messages : [];

  // --- Render ---

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
    <div className={`flex h-screen overflow-hidden bg-white dark:bg-gray-950 selection:bg-black selection:text-white`}>
      {/* Sidebar Component */}
      <Sidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={() => createNewSession()}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        onShareSession={handleShareSession}
        onLogout={handleLogout}
        onOpenSettings={() => setCurrentView('settings')}
        onOpenTrademarkSearch={() => setCurrentView('trademark-search')}
        onToggleTheme={toggleTheme}
        isDarkMode={isDarkMode}
        isMobileOpen={isMobileSidebarOpen}
        username={user.username}
        isDesktopOpen={isDesktopSidebarOpen}
        toggleDesktopSidebar={() => setIsDesktopSidebarOpen(!isDesktopSidebarOpen)}
      />

      {/* Mobile Overlay */}
      {isMobileSidebarOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-20 md:hidden"
          onClick={() => setIsMobileSidebarOpen(false)}
        />
      )}

      {/* Main Content */}
      {currentView === 'settings' ? (
        <SettingsPage
          username={user.username}
          onBack={() => setCurrentView('chat')}
          onUsernameChanged={(newUsername) => {
            setUser(prev => prev ? { ...prev, username: newUsername } : null);
          }}
          isDarkMode={isDarkMode}
        />
      ) : currentView === 'trademark-search' ? (
        <TrademarkSearchPage
          onBack={() => setCurrentView('chat')}
          isDarkMode={isDarkMode}
        />
      ) : (
        <div className="flex-1 flex flex-col h-full relative w-full transition-all duration-300">

          {/* Mobile Header */}
          <header className="flex-shrink-0 bg-white dark:bg-gray-950 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between px-4 py-3 md:hidden z-10">
            <button
              onClick={() => setIsMobileSidebarOpen(true)}
              className="p-2 -ml-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
            >
              <Menu className="w-6 h-6" />
            </button>
            <div className="font-semibold text-gray-900 dark:text-gray-100 truncate max-w-[200px]">
              {currentSession?.title || 'Chat'}
            </div>
            <div className="w-8"></div>
          </header>

          {/* Desktop Header / Toolbar */}
          <div className="hidden md:flex items-center justify-between px-6 py-4 bg-white/90 dark:bg-gray-950/90 backdrop-blur z-10">
            <div className="flex items-center gap-3">
              {!isDesktopSidebarOpen && (
                <button
                  onClick={() => setIsDesktopSidebarOpen(true)}
                  className="p-2 text-gray-500 hover:text-black dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
                  title="Hiện thanh bên"
                >
                  <PanelLeftOpen className="w-5 h-5" />
                </button>
              )}
              <div className="font-semibold text-lg text-gray-800 dark:text-gray-200">
                {currentSession?.title}
              </div>
            </div>
            <div className="flex items-center gap-4">
              <ModeSelector mode={chatMode} onModeChange={(mode) => {
                setChatMode(mode);
                if (currentSession) {
                  setSessions(prev => prev.map(s =>
                    s.id === currentSession.id
                      ? { ...s, mode }
                      : s
                  ));
                }
              }} />
              <div className="flex items-center gap-2 px-3 py-1 bg-gray-50 dark:bg-gray-800 rounded-full border border-gray-100 dark:border-gray-700">
                <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                <span className="text-xs font-medium text-gray-500">Online</span>
              </div>
            </div>
          </div>

          {/* Chat Area */}
          <main className="flex-1 overflow-y-auto px-4 md:px-0">
            <div className="max-w-3xl mx-auto h-full py-8 flex flex-col">
              {currentMessages.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-gray-300">
                  <div className="w-16 h-16 bg-gray-50 rounded-2xl flex items-center justify-center mb-6">
                    <Bot className="w-8 h-8 text-gray-400" />
                  </div>
                  <p className="font-light text-lg text-gray-400">
                    {chatMode === 'smart'
                      ? 'Hỏi bất kỳ câu hỏi nào — tôi sẽ tự động tìm nguồn phù hợp'
                      : chatMode === 'verdict'
                        ? 'Hãy mô tả tình huống pháp lý để tôi phân tích dựa trên bản án'
                        : 'Tôi có thể giúp gì cho bạn hôm nay?'}
                  </p>
                </div>
              ) : (
                <>
                  {currentMessages.map((msg) => (
                    <MessageBubble key={msg.id} message={msg} />
                  ))}

                  {isLoading && (
                    <div className="flex justify-start mb-8 animate-pulse">
                      <div className="flex flex-row gap-4 items-center">
                        <div className="w-8 h-8 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 flex items-center justify-center">
                          <Bot className="w-4 h-4 text-black" />
                        </div>
                        <TypingIndicator />
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} className="h-4" />
                </>
              )}
            </div>
          </main>

          {/* Input Area */}
          <footer className="flex-shrink-0 bg-white dark:bg-gray-950">
            <InputArea onSend={handleSendMessage} disabled={isLoading} />
          </footer>
        </div>
      )}
    </div>
  );
};

export default App;