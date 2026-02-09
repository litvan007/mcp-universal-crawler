# mcp-universal-crawler

MCP server that exposes Futurepedia crawling logic as tools for assistants.

## What it does

- Fetches a random AI tool from Futurepedia search API
- Opens the tool detail page
- Extracts structured fields (description, what is, key features, pros/cons, who uses, image)
- Returns clean JSON for downstream assistant use

## MCP tools

Futurepedia-specific:
- `futurepedia_random_tool()` — get one random tool with parsed metadata
- `futurepedia_tools(count=3)` — get several random tools in one call

Universal crawler:
- `crawl_url(url, timeout_sec=30)` — parse generic webpage (text + title + links)
- `crawl_many(urls, timeout_sec=30)` — batch crawl up to 20 URLs
- `crawl_sitemap(sitemap_url, limit=20, timeout_sec=30)` — extract URLs from sitemap.xml
- `crawl_file(source, timeout_sec=30)` — parse local/remote txt/md/html/pdf/docx
- `extract_structured(url, schema_json, timeout_sec=30)` — CSS-selector extraction by schema

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m futurepedia_mcp.server
```

The server runs over stdio (default MCP mode).

## Claude Desktop / MCP client config

```json
{
  "mcpServers": {
    "futurepedia": {
      "command": "python",
      "args": ["-m", "futurepedia_mcp.server"],
      "cwd": "/absolute/path/to/mcp-universal-crawler"
    }
  }
}
```

## Environment

Optional:

- `PROXY_URL` — proxy URL used for HTTP requests

## Notes

Crawler logic is adapted from `litvan007/AI-slop-tg` (`src/futurepedia.py`) and wrapped for MCP usage.
