# Maharani JSON Extractor

A clean GitHub Codespaces setup to build a daily `dist/heygen_knowledge.txt`
file for your HeyGen bot context.

- Cloud dev: Python 3.11 + Node 20 via devcontainer
- Daily GitHub Action (no SMTP): posts run status as an Issue comment and @mentions you
- Minimal builder (no dependencies) you can extend later to Firecrawl/Apify

## Quick Start

1) Create a new **private** repo named `maharani-json-extractor`.
2) Upload **the contents of this folder** (don’t nest inside another folder).
3) In the repo, open **Code → Create codespace on main**.
4) Run locally in Codespaces:
   ```bash
   python scripts/build_heygen_knowledge.py
   ```
   → Check `dist/heygen_knowledge.txt`.

5) Trigger the workflow manually: **Actions → Daily HeyGen Knowledge Build → Run workflow**.

### Notifications (no SMTP)
- The workflow posts a comment to **Issues** on a tracking issue titled
  *Nightly HeyGen build status* and will `@anandgohel` by default.
- Ensure: Repo **Watch → Custom → Issues** and Profile **Settings → Notifications → Participating & @mentions** are on.

### Secrets (optional for now)
If/when you add API-based crawling:
- **Codespaces secrets** (runtime): `FIRECRAWL_API_KEY`, `APIFY_TOKEN`
- **Actions secrets** (CI): `FIRECRAWL_API_KEY`, `APIFY_TOKEN`

## Structure
```
.devcontainer/devcontainer.json
.github/workflows/daily_build.yml
.vscode/extensions.json
scripts/build_heygen_knowledge.py
requirements.txt
sources.yaml
README.md
.gitignore
```

## Notes
- Keep everything at the **repo root** exactly as above.
- You can later swap in a richer builder and non-empty `requirements.txt`.
