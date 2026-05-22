from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyHit:
    rule_id: str
    label: str
    severity: str
    evidence: str


def _first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return None


PROMPT_INJECTION_RULES = [
    (
        "override-instructions",
        "尝试覆盖之前的指令",
        "high",
        [
            r"\bignore\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|policy)\b",
            r"\bdisregard\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|policy)\b",
            r"忽略.*(规则|指令|限制|策略)",
            r"不用遵守.*(规则|指令|限制|策略)",
            r"覆盖.*(规则|指令|限制|策略)",
        ],
    ),
    (
        "system-prompt-extraction",
        "尝试获取隐藏的系统指令",
        "high",
        [
            r"\b(system|developer)\s+(prompt|message|instruction)s?\b",
            r"\breveal\s+(your\s+)?(prompt|hidden instructions|policy)\b",
            r"\bprint\s+(your\s+)?(prompt|hidden instructions|policy)\b",
            r"系统提示词",
            r"隐藏(规则|指令|策略)",
            r"开发者消息",
            r"把.*(规则|指令|策略).*打印",
        ],
    ),
    (
        "role-play-bypass",
        "角色扮演或越狱绕过",
        "medium",
        [
            r"\b(jailbreak|DAN mode|do anything now)\b",
            r"\bpretend\s+to\s+be\s+(admin|root|developer)\b",
            r"\bact\s+as\s+(admin|root|developer)\b",
            r"假装.*(管理员|开发者|系统)",
            r"扮演.*(管理员|开发者|系统)",
        ],
    ),
    (
        "policy-bypass",
        "尝试绕过安全控制",
        "medium",
        [
            r"\bbypass\s+(the\s+)?(policy|filter|guard|security)\b",
            r"\bdisable\s+(the\s+)?(policy|filter|guard|security)\b",
            r"绕过.*(安全|过滤|权限|策略)",
            r"关闭.*(安全|过滤|权限|策略)",
        ],
    ),
]


SENSITIVE_REQUEST_RULES = [
    (
        "credential-request",
        "请求获取凭据或机密信息",
        "high",
        [
            r"\b(password|passcode|token|secret|api[_ -]?key|private key)\b",
            r"(密码|口令|令牌|密钥|私钥|API\s*key)",
        ],
    ),
    (
        "private-record-request",
        "请求获取私人个人信息或学术记录",
        "high",
        [
            r"\b(all\s+students?|student\s+list|phone|email|grade|GPA|score)\b",
            r"(所有学生|学生名单|手机号|邮箱|联系方式|成绩|绩点|分数)",
        ],
    ),
]


PII_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "phone": r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)",
    "student_id": r"\bS\d{8,12}\b",
}


def detect_prompt_injection(text: str) -> list[PolicyHit]:
    hits: list[PolicyHit] = []
    for rule_id, label, severity, patterns in PROMPT_INJECTION_RULES:
        evidence = _first_match(patterns, text)
        if evidence:
            hits.append(PolicyHit(rule_id, label, severity, evidence))
    return hits


def detect_sensitive_request(text: str) -> list[PolicyHit]:
    hits: list[PolicyHit] = []
    for rule_id, label, severity, patterns in SENSITIVE_REQUEST_RULES:
        evidence = _first_match(patterns, text)
        if evidence:
            hits.append(PolicyHit(rule_id, label, severity, evidence))
    return hits


PII_LABELS = {
    "email": "邮箱地址",
    "phone": "手机号码",
    "student_id": "学号",
}


def detect_pii(text: str) -> list[PolicyHit]:
    hits: list[PolicyHit] = []
    for key, pattern in PII_PATTERNS.items():
        match = re.search(pattern, text)
        if match:
            hits.append(
                PolicyHit(
                    rule_id=f"pii-{key}",
                    label=f"检测到{PII_LABELS.get(key, key)}",
                    severity="medium",
                    evidence=match.group(0),
                )
            )
    return hits


def redact_pii(text: str) -> str:
    redacted = text
    redacted = re.sub(PII_PATTERNS["email"], "[REDACTED_EMAIL]", redacted)
    redacted = re.sub(PII_PATTERNS["phone"], "[REDACTED_PHONE]", redacted)
    redacted = re.sub(PII_PATTERNS["student_id"], "[REDACTED_STUDENT_ID]", redacted)
    return redacted


def highest_risk(hits: list[PolicyHit]) -> str:
    severities = {hit.severity for hit in hits}
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    if hits:
        return "low"
    return "none"
