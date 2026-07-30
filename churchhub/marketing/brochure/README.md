# ChurchHub Brochure Package

| Asset | Path |
|-------|------|
| Full brochure (Markdown) | [`CHURCHHUB_ENTERPRISE_BROCHURE.md`](./CHURCHHUB_ENTERPRISE_BROCHURE.md) |
| **PDF (ReportLab)** | [`ChurchHub_Enterprise_Brochure.pdf`](./ChurchHub_Enterprise_Brochure.pdf) |
| Print HTML + CSS | [`brochure_print.html`](./brochure_print.html) |
| PDF generator script | [`generate_brochure_pdf.py`](./generate_brochure_pdf.py) |
| Screenshot shot list (brochure core 12) | [`SCREENSHOT_SHOT_LIST.md`](./SCREENSHOT_SHOT_LIST.md) |
| Screenshot checklist (by module + priority) | [`SCREENSHOT_CHECKLIST.md`](./SCREENSHOT_CHECKLIST.md) |

## Generate / regenerate the PDF

From the repository root:

```bash
python churchhub/marketing/brochure/generate_brochure_pdf.py
```

Requires `reportlab` (already in `requirements.txt`).

## Alternate print path (HTML)

1. Open `brochure_print.html` in a browser.
2. Print → **Save as PDF**.
3. Use **A4**, enable **Background graphics**.

**Suggested next steps**

1. Capture screenshots into `../screenshots/` using [`SCREENSHOT_CHECKLIST.md`](./SCREENSHOT_CHECKLIST.md) (start with P1).
2. Adapt the brochure into slides under `../presentation/`.
3. Record a walkthrough using `../demo-script/`.
4. Publish selected sections on `../website/`.
