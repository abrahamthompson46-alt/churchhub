#!/usr/bin/env python3
"""Apply ChurchHub design system patterns to HTML templates."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = [
    "templates/transactions",
    "templates/members",
    "templates/announcements",
    "templates/meetings",
    "templates/reports",
    "templates/budgets",
    "templates/giving",
    "templates/organization",
    "templates/accounts",
    "templates/dashboard",
]
SKIP = {
    "templates/members/list.html",
    "templates/dashboard/home.html",
}


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


def table_card_to_data_card(content: str) -> str:
    content = re.sub(
        r'<div class="card">\s*<div class="table-responsive">',
        '<div class="data-card"><div class="table-responsive">',
        content,
    )
    content = re.sub(
        r'<div class="card mb-4">\s*<div class="table-responsive">',
        '<div class="data-card mb-4"><div class="table-responsive">',
        content,
    )
    return content


def filter_card_to_bar(content: str) -> str:
    pattern = (
        r'<div class="card mb-4">\s*<div class="card-body">\s*'
        r'(<form method="get"[^>]*>.*?</form>)\s*</div>\s*</div>'
    )

    def repl(m):
        form = m.group(1)
        form = re.sub(r'class="form-label small"', 'class="form-label"', form)
        return f'<div class="filter-bar">\n        {form}\n    </div>'

    return re.sub(pattern, repl, content, flags=re.DOTALL)


def fix_table_classes(content: str) -> str:
    content = re.sub(
        r'class="table table-hover align-middle mb-0"',
        'class="table table-hover mb-0"',
        content,
    )
    return content


def fix_empty_states(content: str) -> str:
    content = re.sub(
        r'<td colspan="(\d+)">\s*<div class="empty-state">\s*'
        r'<i class="bi ([^"]+) d-block"></i>\s*'
        r'<p class="mb-0">([^<]+)</p>\s*</div>\s*</td>',
        r'<td colspan="\1">{% include "includes/empty_state.html" with icon="bi \2" message="\3" %}</td>',
        content,
        flags=re.DOTALL,
    )
    content = re.sub(
        r'<td colspan="(\d+)" class="text-center text-muted py-4">([^<]+)</td>',
        r'<td colspan="\1">{% include "includes/empty_state.html" with message="\2" %}</td>',
        content,
    )
    content = re.sub(
        r'<tr><td colspan="(\d+)" class="text-muted p-3">([^<]+)</td></tr>',
        r'<tr><td colspan="\1">{% include "includes/empty_state.html" with message="\2" %}</td></tr>',
        content,
    )
    content = re.sub(
        r'<tr><td colspan="(\d+)"><div class="empty-state"><p class="mb-0">([^<]+)</p></div></td></tr>',
        r'<tr><td colspan="\1">{% include "includes/empty_state.html" with message="\2" %}</td></tr>',
        content,
    )
    return content


def add_form_card_wrapper(content: str) -> str:
    """Wrap form card bodies in form-card div."""
    pattern = (
        r'(<div class="col-lg-[78]">\s*'
        r'(?:<nav aria-label="breadcrumb" class="mb-3">.*?</nav>\s*)?'
        r'(?:{% include "includes/page_header.html"[^%]*%}\s*)?)'
        r'<div class="card">'
    )
    if re.search(pattern, content, flags=re.DOTALL):
        content = re.sub(pattern, r"\1<div class=\"form-card\"><div class=\"card\">", content, count=1, flags=re.DOTALL)
        # Close form-card before col-lg closes (before last two closing divs in row)
        content = re.sub(
            r'(</div>\s*</div>\s*)(</div>\s*</div>\s*</div>\s*{% endblock %})',
            r"\1            </div>\n        \2",
            content,
            count=1,
        )
    # col-lg-7 without page_header
    pattern2 = (
        r'(<div class="row justify-content-center">\s*<div class="col-lg-7">\s*)'
        r'<div class="card">'
    )
    if '<div class="form-card">' not in content:
        content = re.sub(pattern2, r'\1<div class="form-card"><div class="card">', content, count=1)
        if '<div class="form-card">' in content:
            content = re.sub(
                r'(</div></div>\s*</div></div>\s*</div>\s*{% endblock %})',
                r'            </div>\n        </div></div>\n    </div></div>\n</div>\n{% endblock %}',
                content,
                count=1,
            )
    return content


def remove_duplicate_module_tabs(content: str) -> str:
    """Remove Published/My Submissions btn-group from announcement_list."""
    pattern = (
        r'\s*<div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">\s*'
        r'<div class="btn-group btn-group-sm">\s*'
        r'<a href="{% url \'announcements:announcement_list\' %}"[^>]*>Published</a>\s*'
        r'<a href="{% url \'announcements:my_announcements\' %}"[^>]*>My Submissions</a>\s*'
        r'</div>\s*'
        r'(<a href="{% url \'announcements:create_announcement\' %}"[^>]*>.*?</a>\s*)'
        r'</div>'
    )
    def repl(m):
        return (
            '\n    {% url \'announcements:create_announcement\' as create_url %}\n'
            '    {% include "includes/page_header.html" with page_subtitle="Communications" '
            'page_title="Announcements" page_description="Approved announcements for your church." '
            'action_url=create_url action_label="Create Announcement" %}\n'
        )
    if "announcement_list" in content and "Published</a>" in content:
        # Replace duplicate header + tabs with single header including action
        content = re.sub(
            r'{% include "includes/page_header.html" with page_subtitle="Communications" page_title="Announcements" page_description="Approved announcements for your church\." %}\s*'
            + pattern,
            repl,
            content,
            flags=re.DOTALL,
        )
    return content


def collapse_blank_lines(content: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", content)


def process_file(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel in SKIP:
        return False
    text = normalize(path.read_text(encoding="utf-8"))
    orig = text
    text = table_card_to_data_card(text)
    text = filter_card_to_bar(text)
    text = fix_table_classes(text)
    text = fix_empty_states(text)
    text = collapse_blank_lines(text)
    if text != orig:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def main():
    updated = []
    for d in DIRS:
        for p in sorted((ROOT / d).glob("*.html")):
            if process_file(p):
                updated.append(p.relative_to(ROOT).as_posix())
    print(f"Updated {len(updated)} files:")
    for f in updated:
        print(f"  {f}")


if __name__ == "__main__":
    main()
