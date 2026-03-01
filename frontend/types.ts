export type Role = 'user' | 'assistant';
export type ChatMode = 'legal' | 'verdict' | 'smart';

export interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: Date;
  isError?: boolean;
  routeType?: string;
}

export interface ChatSession {
    id: string;
    title: string;
    messages: Message[];
    createdAt: Date;
    mode?: ChatMode;
}

export interface User {
    username: string;
    avatar?: string;
}

export interface ChatState {
  sessions: ChatSession[];
  currentSessionId: string | null;
  isLoading: boolean;
}

// Request payload expected by the backend
export interface QueryRequest {
  query: string;
}

// Response model expected from the backend
export interface QueryResponse {
  response?: string;
  answer?: string;
  result?: string;
  text?: string;
  [key: string]: any; 
}