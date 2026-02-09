from __future__ import annotations

import io
import json
import os
import random
import re
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

FUTUREPEDIA_SEARCH_API_URL = "https://www.futurepedia.io/api/search"
BASE_TOOL_URL = "https://www.futurepedia.io/tool/"

mcp = FastMCP("universal-crawler")


def _session() -> requests.Session:
    s = requests.Session()
    proxy = os.getenv("PROXY_URL", "").strip()
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; futurepedia-mcp/0.2)",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        }
    )
    return s


def _fetch_random_meta(s: requests.Session) -> dict[str, str]:
    payload = {"query": "", "page": 1, "sort": "new"}
    r = s.post(FUTUREPEDIA_SEARCH_API_URL, json=payload, timeout=20)
    r.raise_for_status()
    data = r.json()
    items = data.get("data") or []
    if not items:
        raise RuntimeError("Futurepedia search returned no items")

    tool = random.choice(items)
    slug_field = tool.get("slug")
    slug = ""
    if isinstance(slug_field, dict):
        slug = (slug_field.get("current") or "").strip()
    elif isinstance(slug_field, str):
        slug = slug_field.strip()

    if not slug:
        raise RuntimeError("Futurepedia item missing slug")

    return {
        "slug": slug,
        "name": (tool.get("toolName") or "").strip(),
        "short_description": (tool.get("toolShortDescription") or "").strip(),
        "website_url": (tool.get("websiteUrl") or "").strip(),
    }


def _extract_text(soup: BeautifulSoup, selector: str) -> str:
    el = soup.select_one(selector)
    return el.get_text(" ", strip=True) if el else ""


def _extract_meta(soup: BeautifulSoup, key: str, by: str = "property") -> str:
    el = soup.find("meta", attrs={by: key})
    if el and el.get("content"):
        return el["content"].strip()
    return ""


def _extract_section_list(soup: BeautifulSoup, title: str) -> list[str]:
    needle = title.strip().lower()
    for h in soup.find_all(["h2", "h3", "h4"]):
        htxt = h.get_text(" ", strip=True).lower()
        if not htxt.startswith(needle):
            continue
        for sib in h.find_next_siblings():
            if getattr(sib, "name", None) in {"h2", "h3", "h4"}:
                return []
            if getattr(sib, "name", None) in {"ul", "ol"}:
                return [
                    li.get_text(" ", strip=True)
                    for li in sib.find_all("li")
                    if li.get_text(" ", strip=True)
                ]
    return []


def _extract_section_text(soup: BeautifulSoup, title: str) -> str:
    needle = title.strip().lower()
    for h in soup.find_all(["h2", "h3", "h4"]):
        htxt = h.get_text(" ", strip=True).lower()
        if not htxt.startswith(needle):
            continue
        parts: list[str] = []
        for sib in h.find_next_siblings():
            if getattr(sib, "name", None) in {"h2", "h3", "h4"}:
                break
            if getattr(sib, "name", None) == "p":
                txt = sib.get_text(" ", strip=True)
                if txt:
                    parts.append(txt)
            if getattr(sib, "name", None) in {"ul", "ol"}:
                items = [li.get_text(" ", strip=True) for li in sib.find_all("li")]
                items = [i for i in items if i]
                if items:
                    parts.append("; ".join(items))
        return " ".join(parts).strip()
    return ""


def _extract_what_is(soup: BeautifulSoup) -> str:
    for h in soup.find_all(["h2", "h3", "h4"]):
        t = h.get_text(" ", strip=True)
        if not t.lower().startswith("what is"):
            continue
        parts: list[str] = []
        for sib in h.find_next_siblings():
            if getattr(sib, "name", None) in {"h2", "h3", "h4"}:
                break
            if getattr(sib, "name", None) == "p":
                txt = sib.get_text(" ", strip=True)
                if txt:
                    parts.append(txt)
        return " ".join(parts).strip()
    return ""


def _parse_tool_page(html: str, fallback: dict[str, str], url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    name = _extract_text(soup, "h1") or _extract_meta(soup, "og:title") or fallback.get("name", "")
    description = (
        _extract_meta(soup, "og:description")
        or _extract_meta(soup, "description", by="name")
        or fallback.get("short_description", "")
    )
    if not description:
        raise RuntimeError("Tool page has no description")

    return {
        "name": name,
        "description": description,
        "url": url,
        "website_url": fallback.get("website_url", ""),
        "what_is": _extract_what_is(soup),
        "key_features": _extract_section_list(soup, "Key Features"),
        "pros": _extract_section_list(soup, "Pros"),
        "cons": _extract_section_list(soup, "Cons"),
        "who_uses": _extract_section_text(soup, "Who is Using"),
        "og_image": _extract_meta(soup, "og:image"),
    }


def _fetch_one() -> dict[str, Any]:
    s = _session()
    meta = _fetch_random_meta(s)
    url = f"{BASE_TOOL_URL}{meta['slug']}"

    r = s.get(url, timeout=20)
    r.raise_for_status()
    return _parse_tool_page(r.text, meta, url)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_html_content(html: str, url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_text(soup, "title") or _extract_text(soup, "h1")
    description = _extract_meta(soup, "description", by="name") or _extract_meta(soup, "og:description")

    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = _clean_text(main.get_text(" ", strip=True))

    links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        if href in seen:
            continue
        seen.add(href)
        links.append(href)
        if len(links) >= 50:
            break

    return {
        "type": "html",
        "url": url,
        "title": title,
        "description": description,
        "text": text,
        "text_length": len(text),
        "links": links,
    }


def _extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("PDF support requires pypdf") from exc

    reader = PdfReader(io.BytesIO(data))
    pages: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
    return _clean_text("\n".join(pages))


def _extract_docx_text(data: bytes) -> str:
    try:
        from docx import Document
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("DOCX support requires python-docx") from exc

    doc = Document(io.BytesIO(data))
    return _clean_text("\n".join(p.text for p in doc.paragraphs if p.text.strip()))


def _extract_file_content(data: bytes, source: str) -> dict[str, Any]:
    path = source.lower().split("?")[0]

    if path.endswith(".pdf"):
        text = _extract_pdf_text(data)
        return {"type": "pdf", "source": source, "text": text, "text_length": len(text)}

    if path.endswith(".docx"):
        text = _extract_docx_text(data)
        return {"type": "docx", "source": source, "text": text, "text_length": len(text)}

    text = data.decode("utf-8", errors="ignore")
    if path.endswith((".md", ".markdown")):
        return {"type": "markdown", "source": source, "text": _clean_text(text), "text_length": len(_clean_text(text))}
    if path.endswith((".txt", ".log", ".csv", ".json", ".xml")):
        return {"type": "text", "source": source, "text": _clean_text(text), "text_length": len(_clean_text(text))}

    if "<html" in text.lower() or "<!doctype html" in text.lower():
        parsed = _extract_html_content(text, source)
        parsed["type"] = "html-file"
        return parsed

    return {"type": "binary-or-unknown", "source": source, "text": "", "text_length": 0}


def _download(url: str, timeout_sec: int = 30) -> requests.Response:
    s = _session()
    r = s.get(url, timeout=timeout_sec)
    r.raise_for_status()
    return r


@mcp.tool()
def futurepedia_random_tool() -> dict[str, Any]:
    """Fetch one random Futurepedia tool with structured fields."""
    return _fetch_one()


@mcp.tool()
def futurepedia_tools(count: int = 3) -> list[dict[str, Any]]:
    """Fetch several random Futurepedia tools (1..10)."""
    count = max(1, min(10, int(count)))
    return [_fetch_one() for _ in range(count)]


@mcp.tool()
def crawl_url(url: str, timeout_sec: int = 30) -> dict[str, Any]:
    """Fetch and parse a webpage into plain text + metadata."""
    r = _download(url, timeout_sec=timeout_sec)
    ctype = (r.headers.get("content-type") or "").lower()
    if "text/html" not in ctype and "application/xhtml" not in ctype:
        return {
            "type": "non-html",
            "url": url,
            "content_type": ctype,
            "size_bytes": len(r.content),
        }
    return _extract_html_content(r.text, url)


@mcp.tool()
def crawl_many(urls: list[str], timeout_sec: int = 30) -> list[dict[str, Any]]:
    """Crawl multiple URLs and return parsed results."""
    results: list[dict[str, Any]] = []
    for url in urls[:20]:
        try:
            results.append(crawl_url(url=url, timeout_sec=timeout_sec))
        except Exception as exc:
            results.append({"type": "error", "url": url, "error": str(exc)})
    return results


@mcp.tool()
def crawl_sitemap(sitemap_url: str, limit: int = 20, timeout_sec: int = 30) -> dict[str, Any]:
    """Load sitemap.xml and return a list of URLs (limited)."""
    r = _download(sitemap_url, timeout_sec=timeout_sec)
    root = ElementTree.fromstring(r.content)

    urls: list[str] = []
    for node in root.iter():
        tag = node.tag.lower()
        if tag.endswith("loc") and node.text:
            urls.append(node.text.strip())

    limit = max(1, min(200, int(limit)))
    return {
        "sitemap_url": sitemap_url,
        "total_urls": len(urls),
        "urls": urls[:limit],
    }


@mcp.tool()
def crawl_file(source: str, timeout_sec: int = 30) -> dict[str, Any]:
    """Extract text from local file path or HTTP URL (txt/md/html/pdf/docx)."""
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        r = _download(source, timeout_sec=timeout_sec)
        return _extract_file_content(r.content, source)

    if not os.path.exists(source):
        raise RuntimeError(f"File not found: {source}")

    with open(source, "rb") as f:
        data = f.read()
    return _extract_file_content(data, source)


@mcp.tool()
def extract_structured(url: str, schema_json: str, timeout_sec: int = 30) -> dict[str, Any]:
    """Extract fields from HTML by CSS selectors.

    schema_json format:
    {
      "title": "h1",
      "price": ".price",
      "items": [".feature li"]
    }
    """
    schema = json.loads(schema_json)
    r = _download(url, timeout_sec=timeout_sec)
    soup = BeautifulSoup(r.text, "html.parser")

    out: dict[str, Any] = {"url": url, "fields": {}}
    for key, selector in schema.items():
        if isinstance(selector, str):
            out["fields"][key] = _extract_text(soup, selector)
        elif isinstance(selector, list) and selector and isinstance(selector[0], str):
            out["fields"][key] = [
                el.get_text(" ", strip=True) for el in soup.select(selector[0]) if el.get_text(" ", strip=True)
            ]
        else:
            out["fields"][key] = None
    return out


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
