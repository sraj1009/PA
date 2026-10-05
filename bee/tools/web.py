"""web_fetch / web_search — httpx + HTML->text, DuckDuckGo (no API key)."""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from .base import truncate

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


@dataclass
class T:
    name: str
    description: str
    parameters: dict
    handler: object


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|section|article)>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
               .replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"')
               .replace("&quot;", '"').replace("&#x27;", "'"))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _fetch(url: str, timeout: int = 20, limit: int = 10000) -> dict:
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=timeout,
                      follow_redirects=True, verify=True)
    except Exception as e:
        return {"error": f"fetch failed: {e}", "url": url}
    ctype = r.headers.get("content-type", "")
    text = _html_to_text(r.text) if "html" in ctype or r.text.lstrip()[:1] == "<" else r.text
    return {"url": str(r.url), "status": r.status_code, "content_type": ctype,
            "chars": len(text), "content": truncate(text, limit)}


_last_engine = [""]


def _search_ddg_html(query: str, max_results: int = 5) -> list[dict]:
    """html.duckduckgo.com - verified working from this network (2026-10 probe)."""
    results = []
    try:
        r = httpx.post("https://html.duckduckgo.com/html/", data={"q": query},
                       headers={"User-Agent": UA}, timeout=15, follow_redirects=True)
        from urllib.parse import parse_qs, unquote, urlparse
        for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S):
            href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if "uddg=" in href:
                href = unquote(parse_qs(urlparse(href).query).get("uddg", [""])[0])
            elif href.startswith("//"):
                href = "https:" + href
            if href.startswith("http"):
                results.append({"title": title, "url": href, "snippet": ""})
                if len(results) >= max_results:
                    break
        for i, s in enumerate(re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', r.text, re.S)):
            if i < len(results):
                results[i]["snippet"] = re.sub(r"<[^>]+>", "", s).strip()[:300]
    except Exception:
        pass
    return results[:max_results]


def _search_bing(query: str, max_results: int = 5) -> list[dict]:
    results = []
    try:
        r = httpx.get("https://www.bing.com/search", params={"q": query, "count": str(max_results)},
                      headers={"User-Agent": UA}, timeout=15)
        # split into organic-result blocks, then take the <h2><a> title link
        # specifically (the first <a> in a block may be an image/ad link)
        for block in re.split(r'<li class="b_algo"', r.text)[1:max_results + 1]:
            h2 = re.search(r"<h2[^>]*>\s*<a[^>]+href=\"(https?://[^\"]+)\"[^>]*>(.*?)</a>", block, re.S)
            if not h2:
                continue
            import html as _html
            url, title = h2.group(1), _html.unescape(re.sub(r"<[^>]+>", "", h2.group(2)).strip())
            sn = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
            import html as _html
            snippet = _html.unescape(re.sub(r"<[^>]+>", "", sn.group(1)).strip())[:300] if sn else ""
            if title:
                results.append({"title": title, "url": url, "snippet": snippet})
    except Exception:
        pass
    return results[:max_results]


def _search_wikipedia(query: str, max_results: int = 5) -> list[dict]:
    results = []
    try:
        r = httpx.get("https://en.wikipedia.org/w/api.php",
                      params={"action": "opensearch", "search": query, "limit": str(max_results),
                              "format": "json", "origin": "*"},
                      headers={"User-Agent": UA}, timeout=10)
        j = r.json()
        results = [{"title": t, "url": u, "snippet": ""} for t, u in zip(j[1], j[3])]
    except Exception:
        pass
    return results[:max_results]


def _search(query: str, max_results: int = 5) -> list[dict]:
    """Multi-engine keyless search. First engine with results wins; chain:
    DuckDuckGo HTML -> Bing -> Wikipedia opensearch."""
    for engine, fn in (("ddg", _search_ddg_html), ("bing", _search_bing),
                       ("wikipedia", _search_wikipedia)):
        got = fn(query, max_results)
        if got:
            _last_engine[0] = engine
            return got
    _last_engine[0] = ""
    return []


def web_tools():
    def h_fetch(ctx, url: str, timeout: int = 20, limit: int = 10000):
        return _fetch(url, timeout, limit)

    def h_search(ctx, query: str, max_results: int = 5):
        res = _search(query, max_results)
        if not res:
            return {"error": "no results / all search endpoints unreachable", "query": query,
                    "suggestion": "try web_fetch on a known URL, or say 'open <url>' to browse it"}
        return {"query": query, "engine": _last_engine[0], "results": res}

    return [
        T("web_fetch", "Fetch a URL and return cleaned text (HTML stripped). Args: url, timeout (s, default 20), limit (max chars, default 10000).",
          {"type": "object", "properties": {"url": {"type": "string"}, "timeout": {"type": "integer"},
                                            "limit": {"type": "integer"}}, "required": ["url"]}, h_fetch),
        T("web_search", "Web search (DuckDuckGo HTML, Bing and Wikipedia fallbacks - no API key). Returns titles/urls/snippets - then web_fetch the best result. Args: query, max_results (default 5).",
          {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}},
           "required": ["query"]}, h_search),
    ]
