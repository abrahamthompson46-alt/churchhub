# ChurchHub Presentation Package

| Asset | Path |
|-------|------|
| **PowerPoint deck** | [`ChurchHub_Enterprise_Pitch.pptx`](./ChurchHub_Enterprise_Pitch.pptx) |
| Outline (animations · icons · charts) | [`POWERPOINT_OUTLINE.md`](./POWERPOINT_OUTLINE.md) |
| Speaker notes | [`SPEAKER_NOTES.md`](./SPEAKER_NOTES.md) |
| Generator | [`generate_pitch_pptx.py`](./generate_pitch_pptx.py) |

## Regenerate the deck

```bash
pip install python-pptx
python churchhub/marketing/presentation/generate_pitch_pptx.py
```

## After open in PowerPoint

1. Apply animations from `POWERPOINT_OUTLINE.md` (Fade / Wipe sequences).
2. Replace emoji stand-ins with Bootstrap Icons or brand SVGs.
3. Drop P1 screenshots from `../brochure/SCREENSHOT_CHECKLIST.md`.
4. Confirm speaker notes are in the Notes pane (already embedded by the generator).
5. Mark all charts **Sample demo data** before external sharing.

## Modes

| Mode | Slides |
|------|--------|
| Live demo | 01–02 → product → 11–12 (05–10 as backup) |
| Pitch only | 01–12 |
| Board PDF | Export; strip animations |
