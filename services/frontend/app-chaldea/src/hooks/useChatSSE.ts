import { useEffect, useRef, useCallback } from 'react';
import { BASE_URL_DEFAULT } from '../api/api';
import { useAppDispatch } from '../redux/store';
import { addMessage, removeMessage } from '../redux/slices/chatSlice';
import type { ChatMessage, ChatChannel } from '../types/chat';

const MAX_RECONNECT_DELAY = 30000;
const INITIAL_RECONNECT_DELAY = 1000;

interface ChatSSEEvent {
  type: string;
  data: ChatMessage | { id: number; channel: ChatChannel };
}

/**
 * Custom hook for Chat SSE connection.
 * Connects to /notifications/chat/stream and dispatches addMessage / removeMessage
 * actions to Redux on incoming events.
 *
 * Follows the same fetch + ReadableStream pattern as useSSE.ts
 * to support Authorization headers.
 *
 * Only connects when an auth token is present in localStorage.
 */
export function useChatSSE(): void {
  const dispatch = useAppDispatch();
  const abortControllerRef = useRef<AbortController | null>(null);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(async () => {
    const token = localStorage.getItem('accessToken');
    if (!token) {
      return;
    }

    // Abort any existing connection
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const fullUrl = `${BASE_URL_DEFAULT}/notifications/chat/stream`;
      const response = await fetch(fullUrl, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Chat SSE connection failed: ${response.status}`);
      }

      if (!response.body) {
        throw new Error('Chat SSE response has no body');
      }

      if (!mountedRef.current) return;

      // Reset reconnect delay on successful connection
      reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (mountedRef.current) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by double newlines
        const parts = buffer.split('\n\n');
        // Keep the last incomplete part in the buffer
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          const lines = part.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6).trim();
              if (dataStr) {
                try {
                  const parsed = JSON.parse(dataStr) as ChatSSEEvent;
                  handleEvent(parsed);
                } catch {
                  // Non-JSON or malformed data — ignore
                }
              }
            }
          }
        }
      }

      // Stream ended normally — attempt reconnect
      if (mountedRef.current) {
        scheduleReconnect();
      }
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        // Connection was intentionally aborted — do not reconnect
        return;
      }

      if (mountedRef.current) {
        scheduleReconnect();
      }
    }
  }, []);

  const handleEvent = useCallback(
    (event: ChatSSEEvent) => {
      switch (event.type) {
        case 'chat_message':
          dispatch(addMessage(event.data as ChatMessage));
          break;
        case 'chat_message_deleted':
          dispatch(
            removeMessage(event.data as { id: number; channel: ChatChannel }),
          );
          break;
        case 'ping':
          // Keepalive — ignore
          break;
        default:
          break;
      }
    },
    [dispatch],
  );

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;

    const delay = reconnectDelayRef.current;
    reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY);

    reconnectTimeoutRef.current = setTimeout(() => {
      if (mountedRef.current) {
        connect();
      }
    }, delay);
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };
  }, [connect]);
}

export default useChatSSE;
