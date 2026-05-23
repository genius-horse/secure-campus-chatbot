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
            r"忘记.*(规则|指令|限制|策略)",
            r"解除.*(规则|指令|限制|策略)",
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
            r"输出.*(规则|指令|策略)",
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
            r"取消.*(安全|过滤|权限|策略)",
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
            r"(紧急联系人|个人隐私|身份信息)",
        ],
    ),
    (
        "exam-leak-request",
        "请求获取考试相关内容",
        "high",
        [
            r"(考试题库|期中题目|期末题目|试题|答案|泄题)",
            r"\b(exam\s+bank|test\s+bank|answer\s+key)\b",
        ],
    ),
]


SOCIAL_ENGINEERING_RULES = [
    (
        "impersonate-it",
        "冒充IT部门",
        "medium",
        [
            r"我是IT部门",
            r"IT部门.*验证.*系统",
            r"技术支持.*需要.*配置",
            r"系统维护.*需要.*(信息|数据)",
        ],
    ),
    (
        "impersonate-teacher",
        "冒充教师",
        "medium",
        [
            r"我是.*教授",
            r"我是.*老师",
            r"我的账号.*问题.*数据",
            r"(教师|教授).*需要.*查看",
        ],
    ),
    (
        "impersonate-admin",
        "冒充管理员",
        "medium",
        [
            r"我是.*管理员",
            r"新来的管理员",
            r"管理.*权限.*(查看|导出)",
        ],
    ),
    (
        "urgency-pressure",
        "紧急施压",
        "medium",
        [
            r"紧急.*安全事件",
            r"立即.*关闭.*过滤",
            r"马上.*导出.*日志",
            r"马上.*关闭.*安全",
        ],
    ),
]


ENCODING_BYPASS_RULES = [
    (
        "base64-bypass",
        "Base64编码绕过尝试",
        "medium",
        [
            r"base64.*编码.*输出",
            r"用base64.*(规则|策略|提示)",
            r"base64.*(系统|隐藏)",
        ],
    ),
    (
        "translation-bypass",
        "翻译/转写绕过",
        "low",
        [
            r"用英文.*(规则|策略)",
            r"翻译成.*再.*(规则|策略)",
        ],
    ),
]


PII_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "phone": r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)",
    "student_id": r"\bS\d{8,12}\b",
}

PII_LABELS = {
    "email": "邮箱地址",
    "phone": "手机号码",
    "student_id": "学号",
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


def detect_social_engineering(text: str) -> list[PolicyHit]:
    hits: list[PolicyHit] = []
    for rule_id, label, severity, patterns in SOCIAL_ENGINEERING_RULES:
        evidence = _first_match(patterns, text)
        if evidence:
            hits.append(PolicyHit(rule_id, label, severity, evidence))
    return hits


def detect_encoding_bypass(text: str) -> list[PolicyHit]:
    hits: list[PolicyHit] = []
    for rule_id, label, severity, patterns in ENCODING_BYPASS_RULES:
        evidence = _first_match(patterns, text)
        if evidence:
            hits.append(PolicyHit(rule_id, label, severity, evidence))
    return hits


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
