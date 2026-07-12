#!/usr/bin/env python3
"""Apply ChurchHub design system patterns to HTML templates - phase 2."""
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
SKIP = {"templates/members/list.html", "templates/dashboard/home.html"}


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


def replace_manual_header(content: str, subtitle: str, title: str, description=None, action_block=None) -> str:
    """Replace common manual header block with page_header include."""
    desc_part = f' page_description="{description}"' if description else ""
    if action_block:
        header = (
            f'{{% url \'{action_block["url_name"]}\' as action_url %}}\n'
            f'    {{% include "includes/page_header.html" with page_subtitle="{subtitle}" '
            f'page_title="{title}"{desc_part} action_url=action_url action_label="{action_block["label"]}" %}}'
        )
    else:
        header = (
            f'{{% include "includes/page_header.html" with page_subtitle="{subtitle}" '
            f'page_title="{title}"{desc_part} %}}'
        )

    # Generic pattern for manual headers
    pattern = (
        r'<div class="(?:d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4|mb-4)">\s*'
        r'<div>\s*'
        r'<p class="page-subtitle mb-1">' + re.escape(subtitle) + r'</p>\s*'
        r'<h1 class="page-title mb-0">' + re.escape(title) + r'</h1>'
    )
    if description:
        pattern += r'(?:\s*<p class="(?:page-description text-muted|text-muted)[^"]*"[^>]*>' + re.escape(description) + r'</p>)?'
    pattern += r'\s*</div>.*?</div>'

    new_content, n = re.subn(pattern, header, content, count=1, flags=re.DOTALL)
    return new_content if n else content


def wrap_form_card(content: str) -> str:
    if '<div class="form-card">' in content:
        return content
    # Pattern: after page_header or breadcrumb, before card with card-body p-4
    patterns = [
        (
            r'({% include "includes/page_header.html"[^%]*%}\s*)<div class="card">\s*<div class="card-body p-4">',
            r'\1<div class="form-card"><div class="card"><div class="card-body p-4">',
        ),
        (
            r'(<div class="col-lg-8">\s*(?:<nav aria-label="breadcrumb"[^>]*>.*?</nav>\s*)?'
            r'{% include "includes/page_header.html"[^%]*%}\s*)<div class="card">\s*<div class="card-body p-4">',
            r'\1<div class="form-card"><div class="card"><div class="card-body p-4">',
        ),
        (
            r'(<div class="row justify-content-center">\s*<div class="col-lg-7">\s*(?:<nav[^>]*>.*?</nav>\s*)?'
            r'(?:{% include "includes/page_header.html"[^%]*%}\s*)?)<div class="card">\s*<div class="card-body p-4">',
            r'\1<div class="form-card"><div class="card"><div class="card-body p-4">',
        ),
        (
            r'(<div class="row justify-content-center">\s*<div class="col-lg-8">\s*<nav[^>]*>.*?</nav>\s*)'
            r'{% include "includes/page_header.html"[^%]*%}\s*<div class="card">\s*<div class="card-body p-4">',
            r'\1{% include "includes/page_header.html" with page_subtitle="PLACEHOLDER" page_title="PLACEHOLDER" %}\n            <div class="form-card"><div class="card"><div class="card-body p-4">',
        ),
    ]
    for pat, rep in patterns:
        if re.search(pat, content, flags=re.DOTALL):
            content = re.sub(pat, rep, content, count=1, flags=re.DOTALL)
            # Add closing form-card div before col closes
            content = re.sub(
                r'(</div>\s*</div>\s*)(\s*</div>\s*</div>\s*</div>\s*{% endblock %})',
                r'\1            </div>\n        \2',
                content,
                count=1,
            )
            break
    return content


def stat_cards_to_metrics(content: str) -> str:
    """Convert row of stat cards to metrics-row."""
    pattern = (
        r'<div class="row g-3 mb-4">\s*'
        r'(<div class="col-md-4"><div class="card"><div class="card-body">'
        r'<p class="text-muted small mb-1">([^<]+)</p>'
        r'<h5 class="(?:text-success|text-danger|mb-0)[^"]*">([^<]+)</h5>'
        r'</div></div></div>\s*){2,}'
        r'</div>'
    )
    # Simpler: three col-md-4 cards pattern
    m = re.search(
        r'<div class="row g-3 mb-4">\s*'
        r'((?:<div class="col-md-4"><div class="card"><div class="card-body">.*?</div></div></div>\s*)+)'
        r'</div>',
        content,
        flags=re.DOTALL,
    )
    if not m:
        return content
    cards_html = m.group(1)
    cards = re.findall(
        r'<div class="col-md-4"><div class="card"><div class="card-body">'
        r'(?:<p class="text-muted small mb-1">|<div class="text-muted small">)([^<]+)</(?:p|div)>'
        r'(?:<h5 class="[^"]*">|<div class="fs-5 fw-semibold">)([^<]+)</(?:h5|div)>',
        cards_html,
        flags=re.DOTALL,
    )
    if len(cards) < 2:
        return content
    metrics = ['    <div class="metrics-row">']
    variants = ["", " metric-card--success", " metric-card--danger", " metric-card--primary"]
    for i, (label, value) in enumerate(cards):
        v = variants[i] if i < len(variants) else ""
        metrics.append(
            f'        <div class="metric-card{v}"><span class="metric-label">{label.strip()}</span>'
            f'<span class="metric-value">{value.strip()}</span></div>'
        )
    metrics.append("    </div>")
    return content.replace(m.group(0), "\n".join(metrics) + "\n")


def add_table_link(content: str) -> str:
    """Add table-link class to common name/reference links in tables."""
    replacements = [
        (
            r'(<td><a href="{% url \'transactions:transaction_detail\' t\.id %}">)',
            r'<td><a href="{% url \'transactions:transaction_detail\' t.id %}" class="table-link">',
        ),
        (
            r'(<td><a href="{% url \'transactions:transaction_detail\' t\.id %}"><code)',
            r'<td><a href="{% url \'transactions:transaction_detail\' t.id %}" class="table-link"><code',
        ),
        (
            r'(<a href="{% url \'members:detail\' member\.id %}">)',
            r'<a href="{% url \'members:detail\' member.id %}" class="table-link">',
        ),
        (
            r'(<td class="fw-semibold">)({{ m\.title }})',
            r'<td><a href="{% url \'meetings:detail\' m.pk %}" class="table-link">\2</a>',
        ),
        (
            r'(<td>{{ row\.member\.full_name }})',
            r'<td><a href="{% url \'giving:member_statement\' row.member.pk %}?year={{ year }}" class="table-link">{{ row.member.full_name }}</a>',
        ),
        (
            r'(<td>{{ e\.title }})',
            r'<td><a href="{% url \'meetings:attendance_detail\' e.pk %}" class="table-link">{{ e.title }}</a>',
        ),
        (
            r'(<td class="fw-semibold">)({{ a\.title\|truncatechars:50 }})',
            r'<td><a href="{% url \'announcements:announcement_detail\' a.pk %}" class="table-link">\2</a>',
        ),
    ]
    for old, new in replacements:
        if old.startswith("(<td class=\"fw-semibold\">") and "meetings:detail" in new:
            if 'class="table-link"' in content and "meetings:detail" in content:
                continue
        content = re.sub(old, new, content)
    # transaction reference link
    content = re.sub(
        r'<td><a href="(\{% url \'transactions:transaction_detail\' t\.id %\})">(<code class="small">)',
        r'<td><a href="\1" class="table-link">\2',
        content,
    )
    return content


def fix_announcement_list(content: str, path: str) -> str:
    if "announcement_list.html" not in path:
        return content
    # Remove duplicate tabs, move create to header
    content = re.sub(
        r'{% include "includes/page_header.html" with page_subtitle="Communications" page_title="Announcements" page_description="Approved announcements for your church\." %}\s*'
        r'\s*<div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">\s*'
        r'<div class="btn-group btn-group-sm">.*?</div>\s*'
        r'<a href="{% url \'announcements:create_announcement\' %}"[^>]*>.*?</a>\s*'
        r'</div>',
        '{% url \'announcements:create_announcement\' as create_url %}\n'
        '    {% include "includes/page_header.html" with page_subtitle="Communications" '
        'page_title="Announcements" page_description="Approved announcements for your church." '
        'action_url=create_url action_label="Create Announcement" %}',
        content,
        flags=re.DOTALL,
    )
    # Fix empty state in announcement cards
    content = re.sub(
        r'<div class="empty-state">\s*<i class="bi bi-megaphone d-block"></i>\s*<p class="mb-0">No announcements yet\.</p>\s*</div>',
        '{% include "includes/empty_state.html" with icon="bi-megaphone" message="No announcements yet." '
        'action_url=create_url action_label="Create announcement" %}',
        content,
    )
    return content


def fix_my_announcements_filters(content: str, path: str) -> str:
    if "my_announcements.html" not in path:
        return content
    content = re.sub(
        r'<div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">\s*'
        r'<div class="btn-group btn-group-sm">(.*?)</div>\s*'
        r'(<a href="{% url \'announcements:create_announcement\' %}"[^>]*>.*?</a>)\s*'
        r'</div>',
        r'<div class="filter-bar">\n        <div class="btn-group btn-group-sm">\1</div>\n    </div>\n'
        r'    <div class="d-flex justify-content-end mb-3">\2</div>',
        content,
        flags=re.DOTALL,
    )
    return content


def fix_meetings_list(content: str, path: str) -> str:
    if path.endswith("meetings/list.html"):
        content = re.sub(
            r'{% include "includes/page_header.html"[^%]*%}\s*'
            r'<div class="d-flex justify-content-end gap-2 mb-3">',
            '{% url \'meetings:create\' as schedule_url %}\n'
            '    {% include "includes/page_header.html" with page_subtitle="Operations" '
            'page_title="Meetings" page_description="Schedule meetings, record minutes, and track decisions." '
            'action_url=schedule_url action_label="Schedule Meeting" %}\n'
            '    <div class="d-flex justify-content-end gap-2 mb-3 d-none">',
            content,
        )
        # Remove hidden duplicate actions div entirely
        content = re.sub(
            r'\s*<div class="d-flex justify-content-end gap-2 mb-3 d-none">.*?</div>',
            "",
            content,
            flags=re.DOTALL,
        )
        content = re.sub(
            r'(<td><a href="{% url \'meetings:detail\' m\.pk %}" class="table-link">)({{ m\.title }})',
            r'<td><a href="{% url \'meetings:detail\' m.pk %}" class="table-link">{{ m.title }}</a>',
            content,
        )
        # Fix title cell - use table-link on title
        content = re.sub(
            r'<td class="fw-semibold">{{ m\.title }}</td>',
            r'<td><a href="{% url \'meetings:detail\' m.pk %}" class="table-link">{{ m.title }}</a></td>',
            content,
        )
    return content


HEADER_MAP = {
    "transaction_list.html": ("Finance", "All Transactions", None),
    "pending.html": ("Finance", "Pending Approvals", None),
    "audit_log.html": ("Finance", "Financial Audit Log", "Immutable record of financial actions."),
    "financial_dashboard.html": ("Finance", "Financial Statement", None),
    "budget_report.html": ("Finance", "Budget vs Actual", None),
    "reconciliation_list.html": ("Finance", "Bank Reconciliations", None),
    "period_list.html": ("Finance", "Financial Period Lock", None),
    "notifications.html": ("Dashboard", "Notifications", None),
    "hierarchy.html": ("Administration", "Organization Hierarchy", "Conference → Zone → District → Church"),
}


def apply_header_map(content: str, filename: str) -> str:
    if filename not in HEADER_MAP:
        return content
    subtitle, title, desc = HEADER_MAP[filename]
    if 'page_header.html' in content and 'page-subtitle' not in content:
        return content
    # Replace manual header
    block = (
        r'<div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">\s*<div>\s*'
        r'<p class="page-subtitle mb-1">' + re.escape(subtitle) + r'</p>\s*'
        r'<h1 class="page-title mb-0">' + re.escape(title) + r'</h1>'
    )
    if desc:
        block += r'(?:\s*<p class="[^"]*mb-0[^"]*">' + re.escape(desc) + r'</p>)?'
    block += r'\s*</div>.*?</div>'
    desc_attr = f' page_description="{desc}"' if desc else ""
    replacement = f'{{% include "includes/page_header.html" with page_subtitle="{subtitle}" page_title="{title}"{desc_attr} %}}'
    return re.sub(block, replacement, content, count=1, flags=re.DOTALL)


def process_file(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel in SKIP:
        return False
    text = normalize(path.read_text(encoding="utf-8"))
    orig = text
    text = apply_header_map(text, path.name)
    text = fix_announcement_list(text, rel)
    text = fix_my_announcements_filters(text, rel)
    text = fix_meetings_list(text, rel)
    text = wrap_form_card(text)
    text = stat_cards_to_metrics(text)
    text = add_table_link(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
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
    print(f"Phase 2 updated {len(updated)} files:")
    for f in updated:
        print(f"  {f}")


if __name__ == "__main__":
    main()
