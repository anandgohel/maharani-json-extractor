from __future__ import annotations
import datetime
from pathlib import Path

# Always run relative to repo root
ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SRC = ROOT / "sources.yaml"
OUT = DIST / "heygen_knowledge.txt"

def read_sources_naive() -> list[str]:
    urls: list[str] = []
    if not SRC.exists():
        return urls
    try:
        for line in SRC.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("- "):
                urls.append(s[2:].strip())
    except Exception:
        pass
    return urls

def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)
    urls = read_sources_naive() or ["https://www.maharaniweddings.com/"]
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    lines = [f"BUILD_TS:{ts}"]
    for url in urls:
        lines.append(f"SOURCE:{url} | Placeholder content. Replace with Firecrawl/Apify later.")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({len(lines)} lines)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
