# Screenshots

This folder holds marketing PNGs captured from a seeded demo.

## Capture now (automated)

With the app running (e.g. `http://127.0.0.1:8001`):

```bash
pip install playwright
python churchhub/marketing/screenshots/capture_marketing_shots.py
```

Uses your installed Chrome/Edge (no Chromium download). Defaults:

| Env | Default |
|-----|---------|
| `CHURCHHUB_BASE_URL` | `http://127.0.0.1:8001` |
| `CHURCHHUB_USER` / `PASSWORD` | `instadmin` / `instadmin123` |
| Platform user | `admin` / `admin12345` |

Writes the core 12 filenames from [`../brochure/SCREENSHOT_SHOT_LIST.md`](../brochure/SCREENSHOT_SHOT_LIST.md).

## Manual capture

Full checklist: [`../brochure/SCREENSHOT_CHECKLIST.md`](../brochure/SCREENSHOT_CHECKLIST.md).

**Rules:** browser zoom 100% · mask PII · PNG @ 2× when possible · demo data only.
