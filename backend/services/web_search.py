"""Web 搜索服务 — 博查 API 集成。"""

import json
import os
import urllib.error
import urllib.request


def get_web_search_config() -> dict | None:
    api_key = os.environ.get("WEB_SEARCH_API_KEY", "").strip()
    if not api_key:
        return None
    return {
        "api_key": api_key,
        "api_base": os.environ.get("WEB_SEARCH_API_BASE", "https://api.bochaai.com/v1/ai/search").strip(),
        "timeout": int(os.environ.get("WEB_SEARCH_TIMEOUT", "10")),
        "max_results": int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "3")),
    }


def is_configured() -> bool:
    return get_web_search_config() is not None


def web_search(query: str) -> list[dict]:
    """调用博查 API 搜索，返回 [{title, url, snippet}]。"""
    config = get_web_search_config()
    if not config:
        return []

    payload = json.dumps({
        "query": query,
        "count": config["max_results"],
    }).encode("utf-8")

    req = urllib.request.Request(
        config["api_base"],
        data=payload,
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=config["timeout"]) as resp:
            body = resp.read().decode("utf-8")
    except Exception:
        return []

    try:
        data = json.loads(body)
        # 兼容博查响应格式
        results = []
        items = data if isinstance(data, list) else data.get("data", {}).get("results", []) or data.get("results", [])
        for item in items[:config["max_results"]]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", "") or item.get("link", ""),
                "snippet": item.get("snippet", "") or item.get("content", "") or item.get("summary", ""),
            })
        return results
    except (json.JSONDecodeError, TypeError):
        return []


def format_web_results(results: list[dict]) -> str:
    """将搜索结果格式化为 LLM 上下文。"""
    if not results:
        return ""
    lines = ["网络搜索结果："]
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r['title']}\n{r['snippet']}\n来源：{r['url']}")
    return "\n\n".join(lines)
