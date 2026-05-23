import { useState, useCallback, useEffect } from 'react';
import type { User } from '../types';
import api from '../api/client';

export function useAuth() {
  const [user, setUser] = useState<User | null>(() => {
    const stored = localStorage.getItem('secureCampusUser');
    return stored ? JSON.parse(stored) : null;
  });
  const [token, setToken] = useState(() => localStorage.getItem('secureCampusToken') || '');
  const [loading, setLoading] = useState(false);

  const login = useCallback(async (username: string, password: string) => {
    setLoading(true);
    try {
      const data = await api('/api/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      localStorage.setItem('secureCampusToken', data.token);
      localStorage.setItem('secureCampusUser', JSON.stringify(data.user));
      setToken(data.token);
      setUser(data.user);
      return data.user as User;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    await api('/api/logout', { method: 'POST', body: '{}' }).catch(() => {});
    localStorage.removeItem('secureCampusToken');
    localStorage.removeItem('secureCampusUser');
    setToken('');
    setUser(null);
  }, []);

  useEffect(() => {
    if (token) {
      api('/api/me').then((data) => {
        if (data.user) {
          setUser(data.user);
          localStorage.setItem('secureCampusUser', JSON.stringify(data.user));
        }
      }).catch(() => {
        logout();
      });
    }
  }, [token, logout]);

  return {
    user,
    token,
    isAdmin: user?.role === 'admin',
    login,
    logout,
    loading,
  };
}
