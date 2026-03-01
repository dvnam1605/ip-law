import { QueryRequest } from '../types';
import type { ChatMode } from '../types';

const API_BASE = `http://${window.location.hostname}:1605`;
const API_URL = `${API_BASE}/api/query`;
const STREAM_API_URL = `${API_BASE}/api/query/stream`;
const VERDICT_STREAM_API_URL = `${API_BASE}/api/verdict/query/stream`;
const SMART_STREAM_API_URL = `${API_BASE}/api/smart/query/stream`;

/**
 * Sends a user query to the backend API (non-streaming).
 */
export const sendQueryToBackend = async (query: string): Promise<string> => {
  try {
    const payload: QueryRequest = { query };

    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Server error: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    const responseText = data.response || data.answer || data.result || data.text || JSON.stringify(data);

    if (typeof responseText !== 'string') {
      return JSON.stringify(responseText);
    }

    return responseText;

  } catch (error) {
    console.error("Failed to fetch from backend:", error);
    throw error;
  }
};

/**
 * Unescape newlines from SSE format
 */
const unescapeSSE = (text: string): string => {
  return text.replace(/\\n/g, '\n').replace(/\\\\/g, '\\');
};

/**
 * Sends a user query to the backend API with streaming response.
 * Calls onChunk callback for each received chunk.
 */
export const sendQueryToBackendStream = async (
  query: string,
  onChunk: (chunk: string, fullText: string) => void,
  onComplete?: (fullText: string) => void,
  onError?: (error: Error) => void,
  mode: ChatMode = 'legal',
  onRoute?: (route: string) => void,
): Promise<void> => {
  try {
    const payload: QueryRequest = { query };
    let url: string;
    if (mode === 'smart') {
      url = SMART_STREAM_API_URL;
    } else if (mode === 'verdict') {
      url = VERDICT_STREAM_API_URL;
    } else {
      url = STREAM_API_URL;
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
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

      // Parse SSE: split by double newline
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

          // Unescape và append
          const chunk = unescapeSSE(data);

          // Check for route metadata from smart router
          const routeMatch = chunk.trim().match(/^__ROUTE__(legal|verdict|combined)__$/);
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