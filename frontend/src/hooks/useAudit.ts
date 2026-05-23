import { useState, useCallback } from 'react';
import type { AuditLog } from '../types';
import api from '../api/client';

export function useAudit() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [summary, setSummary] = useState({ total: 0, blocked: 0, high_risk: 0 });
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async (filters?: Record<string, string>) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', '100');
      if (filters) {
        Object.entries(filters).forEach(([k, v]) => {
          if (v) params.set(k, v);
        });
      }
      const data = await api(`/api/audit?${params.toString()}`);
      const m = await api('/api/audit/metrics');
      setLogs(data.logs);
      setSummary(data.summary);
      setMetrics(m);
    } catch (err: any) {
      console.error('audit refresh failed:', err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const exportCsv = useCallback(async () => {
    const response = await fetch('/api/audit/export?limit=500', {
      headers: {
        Authorization: `Bearer ${localStorage.getItem('secureCampusToken') || ''}`,
      },
    });
    if (!response.ok) throw new Error('导出失败');
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'secure-campus-audit.csv';
    link.click();
    URL.revokeObjectURL(url);
  }, []);

  const runTests = useCallback(async () => {
    const data = await api('/api/security-tests', { method: 'POST', body: '{}' });
    return data;
  }, []);

  return { logs, summary, metrics, loading, refresh, exportCsv, runTests };
}
