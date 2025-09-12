from __future__ import annotations

import os
import sys
import re
import json
from pathlib import Path
from typing import Dict, List, Any, Union

import httpx
import yaml
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SRC = ROOT / "sources.yaml"
OUT_TXT = DIST / "heygen_knowledge.txt"

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
FIRECRAWL_BASE = os.getenv("FIRECRAWL_BASE", "https://api.firecrawl.dev")
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
APIFY_BASE = os.getenv("APIFY_BASE", "https://api.apify.com")

DEBUG = os.getenv("MJE_DEBUG", "0") == "1"


def log(msg: str) -> None:
    if DEBUG:
        print(f"[debug] {msg}", file=sys.stderr)


def clean_text(text: str) -> str:
    return " ".join(text.split()).strip()


def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return clean_text(soup.get_text(" "))


def dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def read_sources() -> Dict[str, Any]:
    if not SRC.exists():
        return {"web": [], "apify": []}
    data = yaml.safe_load(SRC.read_text(encoding="utf-8")) or {}
    data.setdefault("web", [])
    data.setdefault("apify", [])
    return data


def resolve_env_placeholders(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: resolve_env_placeholders(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_env_placeholders(x) for x in obj]
    if isinstance(obj, str):
        def _subst(match):
            var = match.group(1)
            val = os.getenv(var, "")
            if DEBUG and val == "":
                log(f"ENV missing for placeholder {var}")
            return val
        return re.sub(r"\$\{ENV:([A-Za-z_][A-Za-z0-9_]*)\}", _subst, obj)
    return obj


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def simple_fetch(url: str) -> str:
    headers = {"User-Agent": "MaharaniBot/1.0 (+https://www.maharaniweddings.com)"}
    with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.text


def firecrawl_enabled() -> bool:
    return bool(FIRECRAWL_API_KEY)


def _fc_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def firecrawl_scrape(url: str) -> str | None:
    if not firecrawl_enabled():
        return None

    with httpx.Client(timeout=60.0, follow_redirects=True, headers=_fc_headers()) as client:
        try:
            r = client.post(f"{FIRECRAWL_BASE}/v1/scrape", json={"url": url, "formats": ["text", "markdown"]})
            if r.status_code == 200:
                data = r.json()
                text = None
                if isinstance(data, dict):
                    text = data.get("text") or data.get("markdown") or data.get("content")
                if isinstance(text, str) and text.strip():
                    return text
        except Exception as e:
            log(f"firecrawl scrape error for {url}: {e}")

        try:
            r = client.post(f"{FIRECRAWL_BASE}/v1/crawl", json={"url": url, "maxDepth": 0, "returnFormat": "text"})
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    items = data.get("items") or data.get("pages") or []
                    if isinstance(items, list) and items:
                        parts = []
                        for it in items:
                            for k in ("text","markdown","content","rawText"):
                                if isinstance(it.get(k), str):
                                    parts.append(it[k])
                        if parts:
                            return "\n\n".join(parts)
                elif isinstance(r.text, str) and r.text.strip():
                    return r.text
        except Exception as e:
            log(f"firecrawl crawl error for {url}: {e}")

    return None


def build_lines_from_web(urls: List[str]) -> List[str]:
    lines: List[str] = []
    for url in tqdm(urls, desc="web", unit="url"):
        text: str | None = None
        try:
            text = firecrawl_scrape(url)
        except Exception as e:
            print(f"[firecrawl warn] {url}: {e}", file=sys.stderr)
        if not text:
            try:
                html = simple_fetch(url)
                text = extract_text_from_html(html)
            except Exception as e:
                print(f"[fetch warn] {url}: {e}", file=sys.stderr)
                text = None

        if text:
            text = clean_text(text)
            for i in range(0, len(text), 800):
                chunk = text[i:i+800]
                lines.append(f"SRC:WEB {url} | {chunk}")
    return lines


def apify_enabled() -> bool:
    return bool(APIFY_TOKEN)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def apify_run_sync(actor: str, actor_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not apify_enabled():
        return []

    url = f"{APIFY_BASE}/v2/acts/{actor}/run-sync-get-dataset-items"
    params = {"token": APIFY_TOKEN, "clean": "true", "format": "json"}
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        r = client.post(url, params=params, json=actor_input)
        log(f"apify status for {actor}: {r.status_code}")
        r.raise_for_status()

        try:
            data = r.json()
            if isinstance(data, list):
                return data
        except Exception:
            pass

        items = []
        for line in r.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                pass
        return items


def extract_apify_text_fields(item: Dict[str, Any]) -> str:
    candidates = []
    for key in ("caption", "text", "summary", "title", "description", "alt", "content"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())
    if not candidates:
        for k, v in item.items():
            if isinstance(v, str) and len(v) > 20:
                candidates.append(v)
    return clean_text(" ".join(candidates)) if candidates else ""


def build_lines_from_apify(apify_cfg: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    if not apify_cfg:
        return lines
    for cfg in tqdm(apify_cfg, desc="apify", unit="actor"):
        actor = cfg.get("actor")
        actor_input = resolve_env_placeholders(cfg.get("input", {}))
        if not actor:
            continue
        try:
            items = apify_run_sync(actor, actor_input)
            for it in items:
                txt = extract_apify_text_fields(it)
                src = it.get("url") or it.get("link") or it.get("permalink") or actor
                if txt:
                  for i in range(0, len(txt), 800):
                      chunk = txt[i:i+800]
                      lines.append(f"SRC:APIFY {src} | {chunk}")
        except Exception as e:
            print(f"[apify warn] {actor}: {e}", file=sys.stderr)
    return lines


def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)
    cfg = read_sources()
    web_urls = cfg.get("web", [])
    apify_cfg = cfg.get("apify", [])

    all_lines: List[str] = []
    if web_urls:
        all_lines += build_lines_from_web(web_urls)
    if apify_cfg and apify_enabled():
        all_lines += build_lines_from_apify(apify_cfg)
    elif apify_cfg and not apify_enabled():
        print("[apify warn] APIFY_TOKEN not set; skipping apify sources", file=sys.stderr)

    all_lines = [clean_text(x) for x in all_lines if x and x.strip()]
    all_lines = dedupe_keep_order(all_lines)

    OUT_TXT.write_text("\n".join(all_lines), encoding="utf-8")
    print(f"Wrote {OUT_TXT} ({len(all_lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
