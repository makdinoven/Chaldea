import { useEffect, useRef, useCallback, useState } from 'react';
import { BASE_URL_DEFAULT } from '../api/api';

const MAX_RECONNECT_DELAY = 30000;
const INITIAL_RECONNECT_DELAY = 1000;

/**
 * Custom hook for SSE (Server-Sent Events) connection using fetch + ReadableStream.
 * Uses fetch instead of native EventSource to support Authorization headers.
 *
 * @param url - SSE endpoint path (e.g. '/notifications/stream')
 * @param onEvent - Callback invoked with parsed JSON data for each SSE event
 * @returns { connected: boolean }
 */
export function useSSE(
  url: string,
  onEvent: (data: unknown) => void,
): { connected: boolean } {
  const [connected, setConnected] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const onEventRef = useRef(onEvent);

  // Keep onEvent callback ref up to date without triggering reconnect
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  const connect = useCallback(async () => {
    const token = localStorage.getItem('accessToken');
    if (!token) {
      setConnected(false);
      return;
    }

    // Abort any existing connection
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const fullUrl = `${BASE_URL_DEFAULT}${url}`;
      const response = await fetch(fullUrl, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`SSE connection failed: ${response.status}`);
      }

      if (!response.body) {
        throw new Error('SSE response has no body');
      }

      if (!mountedRef.current) return;

      setConnected(true);
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
                  const parsed = JSON.parse(dataStr);
                  onEventRef.current(parsed);
                } catch {
                  // Non-JSON data, pass as string
                  onEventRef.current(dataStr);
                }
              }
            }
          }
        }
      }

      // Stream ended normally — attempt reconnect
      if (mountedRef.current) {
        setConnected(false);
        scheduleReconnect();
      }
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        // Connection was intentionally aborted — do not reconnect
        return;
      }

      if (mountedRef.current) {
        setConnected(false);
        scheduleReconnect();
      }
    }
  }, [url]);

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

      setConnected(false);
    };
  }, [connect]);

  return { connected };
}

export default useSSE;
