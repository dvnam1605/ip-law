import { QueryRequest, AuthResponse, ApiSession, ApiMessage } from '../types';
import type { ChatMode } from '../types';

const API_BASE = `http://${window.location.hostname}:1605`;
const STREAM_API_URL = `${API_BASE}/api/query/stream`;
const VERDICT_STREAM_API_URL = `${API_BASE}/api/verdict/query/stream`;
const SMART_STREAM_API_URL = `${API_BASE}/api/smart/query/stream`;
const TRADEMARK_STREAM_API_URL = `${API_BASE}/api/trademark/analyze/stream`;

// ── Global 401 handler ──────────────────────────────

let _onUnauthorized: (() => void) | null = null;

export function setOnUnauthorized(callback: () => void): void {
  _onUnauthorized = callback;
}

function handleUnauthorized(): void {
  clearToken();
  _onUnauthorized?.();
}

// ── Token management ────────────────────────────────

function getToken(): string | null {
  return localStorage.getItem('auth_token');
}

function setToken(token: string): void {
  localStorage.setItem('auth_token', token);
}

export function clearToken(): void {
  localStorage.removeItem('auth_token');
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

// ── Auth APIs ───────────────────────────────────────

export const registerUser = async (username: string, password: string, confirmPassword: string): Promise<AuthResponse> => {
  const response = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, confirm_password: confirmPassword }),
  });

  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Đăng ký thất bại');
  }

  const data: AuthResponse = await response.json();
  setToken(data.access_token);
  return data;
};

export const loginUser = async (username: string, password: string): Promise<AuthResponse> => {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Đăng nhập thất bại');
  }

  const data: AuthResponse = await response.json();
  setToken(data.access_token);
  return data;
};

export const getMe = async (): Promise<AuthResponse['user'] | null> => {
  const token = getToken();
  if (!token) return null;

  try {
    const response = await fetch(`${API_BASE}/api/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });

    if (response.status === 401) {
      handleUnauthorized();
      return null;
    }
    if (!response.ok) {
      clearToken();
      return null;
    }

    return await response.json();
  } catch {
    return null;
  }
};

export const logoutUser = async (): Promise<void> => {
  const token = getToken();
  if (token) {
    try {
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
    } catch {
      // Ignore errors, still clear token locally
    }
  }
  clearToken();
};

export const changeUsername = async (newUsername: string): Promise<{ username: string }> => {
  const response = await fetch(`${API_BASE}/api/auth/username`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ new_username: newUsername }),
  });
  if (response.status === 401) { handleUnauthorized(); throw new Error('Unauthorized'); }
  if (!response.ok) {
    const data = await response.json();
    throw new Error(data.detail || 'Không thể đổi tên đăng nhập');
  }
  return response.json();
};

export const changePassword = async (
  currentPassword: string,
  newPassword: string,
  confirmPassword: string,
): Promise<void> => {
  const response = await fetch(`${API_BASE}/api/auth/password`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
      confirm_password: confirmPassword,
    }),
  });
  if (response.status === 401) { handleUnauthorized(); throw new Error('Unauthorized'); }
  if (!response.ok) {
    const data = await response.json();
    throw new Error(data.detail || 'Không thể đổi mật khẩu');
  }
};

// ── Session APIs ────────────────────────────────────

export const fetchSessions = async (): Promise<ApiSession[]> => {
  const response = await fetch(`${API_BASE}/api/sessions`, {
    headers: authHeaders(),
  });
  if (response.status === 401) { handleUnauthorized(); throw new Error('Unauthorized'); }
  if (!response.ok) throw new Error('Không thể tải sessions');
  return response.json();
};

export const fetchAdminUsers = async (skip: number = 0, limit: number = 100) => {
  const response = await fetch(`${API_BASE}/api/admin/users?skip=${skip}&limit=${limit}`, {
    headers: authHeaders(),
  });
  if (response.status === 401) { handleUnauthorized(); throw new Error('Unauthorized'); }
  if (response.status === 403) throw new Error('Forbidden');
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const fetchAdminSessions = async (skip: number = 0, limit: number = 100) => {
  const response = await fetch(`${API_BASE}/api/admin/sessions?skip=${skip}&limit=${limit}`, {
    headers: authHeaders(),
  });
  if (response.status === 401) { handleUnauthorized(); throw new Error('Unauthorized'); }
  if (response.status === 403) throw new Error('Forbidden');
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const createSessionApi = async (title: string, mode: string): Promise<ApiSession> => {
  const response = await fetch(`${API_BASE}/api/sessions`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ title, mode }),
  });
  if (!response.ok) throw new Error('Không thể tạo session');
  return response.json();
};

export const renameSessionApi = async (sessionId: string, title: string): Promise<ApiSession> => {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ title }),
  });
  if (!response.ok) throw new Error('Không thể đổi tên session');
  return response.json();
};

export const deleteSessionApi = async (sessionId: string): Promise<void> => {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!response.ok) throw new Error('Không thể xóa session');
};

// ── Message APIs ────────────────────────────────────

export const fetchMessages = async (sessionId: string): Promise<ApiMessage[]> => {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`, {
    headers: authHeaders(),
  });
  if (!response.ok) throw new Error('Không thể tải tin nhắn');
  return response.json();
};

export const saveMessage = async (
  sessionId: string,
  role: string,
  content: string,
  routeType?: string,
): Promise<ApiMessage> => {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ role, content, route_type: routeType || null }),
  });
  if (!response.ok) throw new Error('Không thể lưu tin nhắn');
  return response.json();
};

// ── Admin APIs ──────────────────────────────────────

export const fetchAdminStats = async (): Promise<any> => {
  const response = await fetch(`${API_BASE}/api/admin/stats`, {
    headers: authHeaders(),
  });
  if (response.status === 401) { handleUnauthorized(); throw new Error('Unauthorized'); }
  if (response.status === 403) throw new Error('Forbidden');
  if (!response.ok) throw new Error('Không thể tải admin stats');
  return response.json();
};

// ── Streaming (unchanged logic) ─────────────────────

const unescapeSSE = (text: string): string => {
  return text.replace(/\\n/g, '\n').replace(/\\\\/g, '\\');
};

export const sendQueryToBackendStream = async (
  query: string,
  onChunk: (chunk: string, fullText: string) => void,
  onComplete?: (fullText: string) => void,
  onError?: (error: Error) => void,
  mode: ChatMode = 'legal',
  onRoute?: (route: string) => void,
  sessionId?: string,
): Promise<void> => {
  try {
    const payload: QueryRequest = { query, session_id: sessionId };
    let url: string;
    if (mode === 'smart') {
      url = SMART_STREAM_API_URL;
    } else if (mode === 'verdict') {
      url = VERDICT_STREAM_API_URL;
    } else if (mode === 'trademark') {
      url = TRADEMARK_STREAM_API_URL;
    } else {
      url = STREAM_API_URL;
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Server error: ${response.status} ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Response body is not readable');
    }

    const decoder = new TextDecoder();
    let fullText = '';
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';

      for (const part of parts) {
        if (part.startsWith('data: ')) {
          const data = part.slice(6);

          if (data === '[DONE]') {
            onComplete?.(fullText);
            return;
          }

          if (data.startsWith('[ERROR]')) {
            throw new Error(data.slice(7));
          }

          const chunk = unescapeSSE(data);

          const routeMatch = chunk.trim().match(/^__ROUTE__(legal|verdict|combined|trademark)__$/);
          if (routeMatch) {
            onRoute?.(routeMatch[1]);
            continue;
          }

          fullText += chunk;
          onChunk(chunk, fullText);
        }
      }
    }

    onComplete?.(fullText);

  } catch (error) {
    console.error("Failed to fetch stream from backend:", error);
    onError?.(error as Error);
    throw error;
  }
};