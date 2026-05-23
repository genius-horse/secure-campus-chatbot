# Project Report Outline

## 1. Introduction

This project designs and implements a secure smart campus assistant chatbot. The system answers campus-related questions while defending against prompt injection, private data extraction, and unauthorized access to role-restricted records.

## 2. Background and Literature Survey

Suggested topics to cover:

- Large language model security
- Prompt injection and jailbreak attacks
- Retrieval-augmented generation and knowledge base leakage
- Privacy protection and personally identifiable information
- Role-based access control
- Security audit logging

Suggested references:

- OWASP Top 10 for Large Language Model Applications
- NIST privacy and access control guidance
- Research papers or articles about prompt injection and RAG security
- Course materials about authentication, authorization, and data security

## 3. Project Objectives

- Build a working chatbot for campus information.
- Enforce role-aware access to knowledge base entries.
- Detect and block prompt injection attacks.
- Detect sensitive requests for credentials, personal data, and academic records.
- Record high-risk or blocked requests for administrator review.

## 4. System Design

Main modules:

- Frontend web interface
- HTTP backend API
- Authentication and role management
- Secure chatbot pipeline
- Optional LLM API generation module
- Role-aware retrieval module
- Security detection module
- SQLite audit database

Data flow:

1. User logs in with a role.
2. User sends a message.
3. Security module checks prompt injection and sensitive data requests.
4. Retrieval module searches only role-accessible knowledge.
5. If API mode is enabled, only authorized and redacted context is sent to the external model.
6. Chatbot returns an allowed answer or blocks the request.
7. Audit module records the event.

## 5. Security Model

Protected assets:

- System instructions and safety policy
- Restricted knowledge base records
- Personal contact data
- Student records and grades
- Audit logs

Threats:

- Prompt injection
- Jailbreak role play
- Private data extraction
- Unauthorized retrieval
- Repeated probing

Defenses:

- Pattern-based injection detection
- Role-based access control
- PII redaction
- Deny-by-default for restricted matches
- Audit logging

## 6. Implementation

The project is implemented with Python standard library only. The backend uses `http.server` and SQLite. The frontend uses HTML, CSS, and JavaScript. The local knowledge base is stored in JSON.

The system can optionally call an OpenAI-compatible chat-completions API. This is disabled by default. When enabled, the API is used only as a response generator after local safety checks and role-based retrieval have already completed.

Important files:

- `backend/app.py`: API routes and static file server
- `backend/chatbot.py`: secure response pipeline
- `backend/security.py`: prompt injection and privacy detection
- `backend/retrieval.py`: role-aware knowledge search
- `backend/llm_provider.py`: optional external LLM API client
- `backend/database.py`: audit logging
- `frontend/index.html`: demo interface

## 7. Testing

Test cases:

- Normal campus question should be answered.
- Prompt injection should be blocked.
- Student request for private records should be blocked.
- Teacher-only records should not be shown to students.
- Admin can review audit logs.

## 8. Demo Plan

1. Login as student and ask a public question.
2. Ask about student lab schedule.
3. Try to extract all students' phone numbers and grades.
4. Try prompt injection to reveal hidden rules.
5. Login as teacher and ask grading rubric.
6. Login as admin and view audit logs.

## 9. Conclusion

The project demonstrates how security controls can be integrated into a smart chatbot. It shows that chatbot usefulness and data protection must be designed together, especially when the system uses a knowledge base with mixed sensitivity levels.
