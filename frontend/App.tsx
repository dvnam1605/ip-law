import React, { useState, useRef, useEffect } from 'react';
import { Message, ChatSession, User, ChatMode } from './types';
import {
  sendQueryToBackendStream,
  getMe,
  clearToken,
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

  const handleLogout = () => {
    clearToken();
    setUser(null);
    setSessions([]);
    setCurrentSessionId(null);
  };

  const createNewSession = async (overrideMode?: ChatMode) => {
    const mode = overrideMode || chatMode;
    try {
      const apiSession = await createSessionApi('Đoạn chat mới', mode);
      const welcomeMessages: Record<ChatMode, string> = {
        smart: 'Xin chào! Hãy hỏi bất kỳ câu hỏi nào về Sở hữu trí tuệ — tôi sẽ tự động tìm nguồn phù hợp nhất (luật, bản án, hoặc cả hai).',
        verdict: 'Xin chào! Tôi có thể phân tích tình huống pháp lý dựa trên các bản án thực tế về Sở hữu trí tuệ. Hãy mô tả tình huống của bạn!',
        legal: 'Xin chào! Tôi có thể giúp gì cho bạn về các quy định pháp luật?',
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
        }
      );
    } catch (error) {
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
    <div className="flex h-screen overflow-hidden bg-white selection:bg-black selection:text-white">
      {/* Sidebar Component */}
      <Sidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={createNewSession}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        onShareSession={handleShareSession}
        onLogout={handleLogout}
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
      <div className="flex-1 flex flex-col h-full relative w-full transition-all duration-300">

        {/* Mobile Header */}
        <header className="flex-shrink-0 bg-white border-b border-gray-100 flex items-center justify-between px-4 py-3 md:hidden z-10">
          <button
            onClick={() => setIsMobileSidebarOpen(true)}
            className="p-2 -ml-2 text-gray-600 hover:bg-gray-100 rounded-lg"
          >
            <Menu className="w-6 h-6" />
          </button>
          <div className="font-semibold text-gray-900 truncate max-w-[200px]">
            {currentSession?.title || 'Chat'}
          </div>
          <div className="w-8"></div>
        </header>

        {/* Desktop Header / Toolbar */}
        <div className="hidden md:flex items-center justify-between px-6 py-4 bg-white/90 backdrop-blur z-10">
          <div className="flex items-center gap-3">
            {!isDesktopSidebarOpen && (
              <button
                onClick={() => setIsDesktopSidebarOpen(true)}
                className="p-2 text-gray-500 hover:text-black hover:bg-gray-100 rounded-lg transition-colors"
                title="Hiện thanh bên"
              >
                <PanelLeftOpen className="w-5 h-5" />
              </button>
            )}
            <div className="font-semibold text-lg text-gray-800">
              {currentSession?.title}
            </div>
          </div>
          <div className="flex items-center gap-4">
            <ModeSelector mode={chatMode} onModeChange={(mode) => {
              setChatMode(mode);
              const isCurrentEmpty = currentSession &&
                currentSession.title === 'Đoạn chat mới' &&
                currentSession.messages.length <= 1;
              if (isCurrentEmpty && currentSession) {
                const welcomeMessages: Record<ChatMode, string> = {
                  smart: 'Xin chào! Hãy hỏi bất kỳ câu hỏi nào về Sở hữu trí tuệ — tôi sẽ tự động tìm nguồn phù hợp nhất (luật, bản án, hoặc cả hai).',
                  verdict: 'Xin chào! Tôi có thể phân tích tình huống pháp lý dựa trên các bản án thực tế về Sở hữu trí tuệ. Hãy mô tả tình huống của bạn!',
                  legal: 'Xin chào! Tôi có thể giúp gì cho bạn về các quy định pháp luật?',
                };
                setSessions(prev => prev.map(s =>
                  s.id === currentSession.id
                    ? { ...s, mode, messages: [{ ...s.messages[0], content: welcomeMessages[mode] }] }
                    : s
                ));
              } else {
                createNewSession(mode);
              }
            }} />
            <div className="flex items-center gap-2 px-3 py-1 bg-gray-50 rounded-full border border-gray-100">
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
                      <div className="w-8 h-8 rounded-full bg-white border border-gray-200 flex items-center justify-center">
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
        <footer className="flex-shrink-0 bg-white">
          <InputArea onSend={handleSendMessage} disabled={isLoading} />
        </footer>
      </div>
    </div>
  );
};

export default App;