import { useState, useCallback, useRef } from 'react';
import type { Message, ChatResponse, Session } from '../types';
import api from '../api/client';

export function useChat(token: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [risk, setRisk] = useState<string>('none');
  const [isTyping, setIsTyping] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  // Refs to avoid closure issues in streaming loop
  const streamContentRef = useRef<string>('');
  const activeSessionRef = useRef<string | null>(null);

  // Keep refs in sync
  activeSessionRef.current = activeSessionId;

  // ── Sessions ──

  const loadSessions = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api('/api/sessions');
      setSessions(data.sessions || []);
      setActiveSessionId(data.active_session_id || null);
    } catch { /* ignore */ }
  }, [token]);

  const createSession = useCallback(async (name: string = '新会话') => {
    if (!token) return null;
    try {
      const data = await api('/api/sessions', {
        method: 'POST',
        body: JSON.stringify({ name }),
      });
      setMessages([]);
      setRisk('none');
      setActiveSessionId(data.id);
      await loadSessions();
      return data.id;
    } catch { return null; }
  }, [token, loadSessions]);

  const renameSession = useCallback(async (sessionId: string, name: string) => {
    if (!token) return;
    try {
      await api(`/api/sessions/${sessionId}`, {
        method: 'PUT',
        body: JSON.stringify({ name }),
      });
      await loadSessions();
    } catch { /* ignore */ }
  }, [token, loadSessions]);

  const deleteSession = useCallback(async (sessionId: string) => {
    if (!token) return;
    try {
      const data = await api(`/api/sessions/${sessionId}`, { method: 'DELETE' });
      if (sessionId === activeSessionId) {
        setMessages([]);
        setRisk('none');
        setActiveSessionId(data.active_session_id || null);
        if (data.active_session_id) {
          await switchSession(data.active_session_id);
        }
      }
      await loadSessions();
    } catch { /* ignore */ }
  }, [token, activeSessionId, loadSessions]);

  const switchSession = useCallback(async (sessionId: string) => {
    if (!token) return;
    try {
      const data = await api(`/api/sessions/${sessionId}/activate`, { method: 'POST' });
      setActiveSessionId(sessionId);
      const msgs: Message[] = (data.messages || []).map((m: any) => ({
        role: m.role,
        content: m.content,
      }));
      setMessages(msgs);
      setRisk('none');
      await loadSessions();
    } catch { /* ignore */ }
  }, [token, loadSessions]);

  // ── Normal send ──

  const sendMessage = useCallback(async (text: string, streamEnabled: boolean = true, webEnabled: boolean = false) => {
    if (!token) return;
    setMessages((prev) => [...prev, { role: 'user', content: text }]);

    if (streamEnabled) {
      return sendMessageStream(text, webEnabled);
    }

    setIsTyping(true);
    try {
      const res: ChatResponse = await api('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ message: text, session_id: activeSessionRef.current }),
      });
      setRisk(res.risk);
      setMessages((prev) => [...prev, { role: 'assistant', content: res.answer, meta: res }]);
      if (res.session_id) setActiveSessionId(res.session_id);
    } catch (err: any) {
      setMessages((prev) => [...prev, { role: 'assistant', content: `错误：${err.message}` }]);
    } finally {
      setIsTyping(false);
    }
  }, [token]);

  // ── Streaming send ──

  const sendMessageStream = useCallback(async (text: string, webEnabled: boolean = false) => {
    if (!token) return;
    setIsStreaming(true);
    setStreamingContent('');
    streamContentRef.current = '';
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: text, session_id: activeSessionRef.current, web_enabled: webEnabled }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error((errData as any).detail || `HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('浏览器不支持流式响应');

      const decoder = new TextDecoder();
      let buffer = '';
      let finalMeta: ChatResponse | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (data === '[DONE]') continue;

          try {
            const parsed = JSON.parse(data);
            if (parsed.type === 'meta') {
              setRisk(parsed.risk || 'none');
              if (parsed.session_id) setActiveSessionId(parsed.session_id);
            } else if (parsed.type === 'token') {
              streamContentRef.current += (parsed.token || '');
              setStreamingContent(streamContentRef.current);
            } else if (parsed.type === 'done') {
              finalMeta = parsed;
            }
          } catch { /* skip malformed */ }
        }
      }

      // Finalize
      const finalContent = streamContentRef.current;
      setStreamingContent('');
      setIsStreaming(false);

      if (finalMeta) {
        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: finalContent,
          meta: finalMeta as any,
        }]);
      } else if (finalContent) {
        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: finalContent,
        }]);
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        const partial = streamContentRef.current;
        setStreamingContent('');
        setIsStreaming(false);
        if (partial) {
          setMessages((prev) => [...prev, { role: 'assistant', content: partial + ' [已取消]' }]);
        }
        return;
      }
      setStreamingContent('');
      setIsStreaming(false);
      setMessages((prev) => [...prev, { role: 'assistant', content: `流式错误：${err.message}` }]);
    } finally {
      abortRef.current = null;
    }
  }, [token]);

  const cancelStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // ── Message operations ──

  const clearHistory = useCallback(async () => {
    if (!token) return;
    await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message: '', clear_history: true, session_id: activeSessionRef.current }),
    }).catch(() => {});
    setMessages([]);
    setRisk('none');
  }, [token]);

  const regenerateResponse = useCallback(async () => {
    if (!token) return;
    setIsTyping(true);
    try {
      const res: ChatResponse = await api('/api/chat/regenerate', {
        method: 'POST',
        body: JSON.stringify({ session_id: activeSessionRef.current }),
      });
      setRisk(res.risk);
      setMessages((prev) => {
        const updated = [...prev];
        if (updated.length > 0 && updated[updated.length - 1].role === 'assistant') {
          updated[updated.length - 1] = { role: 'assistant', content: res.answer, meta: res };
        } else {
          updated.push({ role: 'assistant', content: res.answer, meta: res });
        }
        return updated;
      });
      if (res.session_id) setActiveSessionId(res.session_id);
    } catch (err: any) {
      setMessages((prev) => [...prev, { role: 'assistant', content: `重新生成失败：${err.message}` }]);
    } finally {
      setIsTyping(false);
    }
  }, [token]);

  const setMessagesDirect = useCallback((updater: ((prev: Message[]) => Message[]) | Message[]) => {
    setMessages(updater);
  }, []);

  const editMessage = useCallback(async (index: number, newText: string) => {
    if (!token) return;
    // Trim messages to before the edited message, then send
    setMessages((prev) => {
      const updated = prev.slice(0, index);
      return [...updated, { role: 'user', content: newText }];
    });
    setIsTyping(true);
    try {
      const res: ChatResponse = await api('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ message: newText, session_id: activeSessionRef.current }),
      });
      setRisk(res.risk);
      setMessages((prev) => [...prev, { role: 'assistant', content: res.answer, meta: res }]);
      if (res.session_id) setActiveSessionId(res.session_id);
    } catch (err: any) {
      setMessages((prev) => [...prev, { role: 'assistant', content: `错误：${err.message}` }]);
    } finally {
      setIsTyping(false);
    }
  }, [token]);

  return {
    messages, risk, isTyping, isStreaming, streamingContent,
    sessions, activeSessionId,
    sendMessage, sendMessageStream, cancelStreaming,
    clearHistory, regenerateResponse, editMessage, setMessages: setMessagesDirect,
    loadSessions, createSession, renameSession, deleteSession, switchSession,
  };
}
