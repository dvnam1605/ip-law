export type Role = 'user' | 'assistant';
export type ChatMode = 'legal' | 'verdict' | 'smart' | 'trademark';

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
  id: number;
  username: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface ChatState {
  sessions: ChatSession[];
  currentSessionId: string | null;
  isLoading: boolean;
}

// Backend session (from API)
export interface ApiSession {
  id: string;
  title: string;
  mode: string;
  created_at: string;
  updated_at: string;
}

// Backend message (from API)
export interface ApiMessage {
  id: string;
  role: string;
  content: string;
  route_type: string | null;
  created_at: string;
}

// Request payload expected by the backend
export interface QueryRequest {
  query: string;
  session_id?: string;
}

// Response model expected from the backend
export interface QueryResponse {
  response?: string;
  answer?: string;
  result?: string;
  text?: string;
  [key: string]: any;
}

// Trademark types
export interface TrademarkResult {
  brand_name: string;
  owner_name: string;
  owner_country: string;
  registration_number: string;
  nice_classes: string[];
  ipr_type: string;
  country_of_filing: string;
  status: string;
  status_date: string;
  similarity_score: number;
  match_type: string;
}

export interface TrademarkSearchResponse {
  success: boolean;
  query: string;
  results: TrademarkResult[];
  total_found: number;
  processing_time_ms: number;
}