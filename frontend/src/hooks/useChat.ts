import { useState, useCallback } from 'react';
import type { Message, ChatResponse } from '../types';
import api from '../api/client';

export function useChat(token: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [risk, setRisk] = useState<string>('none');
  const [isTyping, setIsTyping] = useState(false);

  const sendMessage = useCallback(async (text: string) => {
    if (!token) return;
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setIsTyping(true);
    try {
      const res: ChatResponse = await api('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ message: text }),
      });
      setRisk(res.risk);
      setMessages((prev) => [...prev, { role: 'assistant', content: res.answer, meta: res }]);
    } catch (err: any) {
      setMessages((prev) => [...prev, { role: 'assistant', content: `错误：${err.message}` }]);
    } finally {
      setIsTyping(false);
    }
  }, [token]);

  const clearHistory = useCallback(async () => {
    if (!token) return;
    await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message: '', clear_history: true }),
    }).catch(() => {});
    setMessages([]);
    setRisk('none');
  }, [token]);

  return { messages, risk, isTyping, sendMessage, clearHistory };
}
