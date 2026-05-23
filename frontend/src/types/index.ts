export interface User {
  username: string;
  display_name: string;
  role: 'public' | 'student' | 'teacher' | 'admin';
}

export interface PolicyHit {
  rule_id: string;
  label: string;
  severity: string;
  evidence: string;
}

export interface Citation {
  id: string;
  title: string;
  sensitivity: string;
  min_role: string;
}

export interface ChatResponse {
  action: 'allowed' | 'blocked' | 'partially_allowed';
  risk: 'none' | 'low' | 'medium' | 'high';
  answer: string;
  policy_hits: PolicyHit[];
  citations: Citation[];
  denied_citations: Citation[];
  audit_id: number | null;
  generation_mode: string;
  llm_error: string | null;
  history_message_count: number;
  history_cleared?: boolean;
  session_id?: string;
  web_citations?: WebCitation[];
}

export interface WebCitation {
  title: string;
  url: string;
  snippet: string;
}

export interface AuditLog {
  id: number;
  created_at: string;
  username: string;
  role: string;
  action: string;
  risk: string;
  message: string;
  response: string;
  policy_hits: PolicyHit[];
  citations: Citation[];
  generation_mode: string;
}

export interface KnowledgeItem {
  id: string;
  title: string;
  min_role: string;
  sensitivity: string;
  keywords: string[];
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  meta?: ChatResponse;
}

export interface Session {
  id: string;
  name: string;
  message_count: number;
  created_at: number;
  updated_at: number;
  is_active: boolean;
}

export interface ToastItem {
  id: number;
  message: string;
  type: 'error' | 'success' | 'warning';
}
