"""One-off template normalizer for ChurchHub UI v2."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent / "templates"
SKIP = {"page_header.html", "form_field.html", "navbar.html", "module_tabs.html", "empty_state.html", "stat_card.html", "base.html"}


def normalize(text: str) -> str:
    text = re.sub(
        r'<div class="card">\s*<div class="table-responsive">',
        '<div class="data-card"><div class="table-responsive">',
        text,
    )
    text = re.sub(
        r'<div class="card mb-4">\s*<div class="table-responsive">',
        '<div class="data-card mb-4"><div class="table-responsive">',
        text,
    )
    text = text.replace('icon="bi bi-', 'icon="bi-')
    if text.count("\n\n\n") > 3:
        text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def main():
    n = 0
    for f in ROOT.rglob("*.html"):
        if f.name in SKIP or "includes" in f.parts and f.parent.name == "includes":
            if f.name in SKIP:
                continue
        orig = f.read_text(encoding="utf-8")
        new = normalize(orig)
        if new != orig:
            f.write_text(new, encoding="utf-8")
            print(f"updated {f.relative_to(ROOT)}")
            n += 1
    print(f"Done: {n} files")


if __name__ == "__main__":
    main()
