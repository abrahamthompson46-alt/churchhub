#!/usr/bin/env python3
"""Phase 3: finish page_header, table-link, form-card, metrics for remaining templates."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"templates/members/list.html", "templates/dashboard/home.html"}

REPLACEMENTS = {
    "templates/members/department_list.html": (
        r'<div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">\s*'
        r'<div>\s*<p class="page-subtitle mb-1">Members</p>\s*'
        r'<h1 class="page-title mb-0">Departments</h1>\s*</div>\s*'
        r'<a href="{% url \'members:department_add\' %}" class="btn btn-primary btn-sm">Add Department</a>\s*</div>',
        '{% url \'members:department_add\' as add_url %}\n'
        '    {% include "includes/page_header.html" with page_subtitle="People" page_title="Departments" '
        'action_url=add_url action_label="Add Department" %}',
    ),
    "templates/members/transfer_list.html": (
        r'<div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">\s*'
        r'<div>\s*<p class="page-subtitle mb-1">Members</p>\s*'
        r'<h1 class="page-title mb-0">Member Transfers</h1>\s*</div>\s*'
        r'<a href="{% url \'members:transfer_create\' %}" class="btn btn-primary btn-sm">Request Transfer</a>\s*</div>',
        '{% url \'members:transfer_create\' as add_url %}\n'
        '    {% include "includes/page_header.html" with page_subtitle="People" page_title="Member Transfers" '
        'action_url=add_url action_label="Request Transfer" %}',
    ),
    "templates/members/record_list.html": (
        r'<div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">\s*'
        r'<div>\s*<p class="page-subtitle mb-1">Members</p>\s*'
        r'<h1 class="page-title mb-0">Member Records</h1>\s*'
        r'<p class="page-description text-muted mb-0 mt-1">Baptism, marriage, transfers, and other spiritual records\.</p>\s*'
        r'</div>\s*'
        r'<a href="{% url \'members:record_add\' %}" class="btn btn-primary btn-sm"><i class="bi bi-journal-plus me-1"></i>Add Record</a>\s*</div>',
        '{% url \'members:record_add\' as add_url %}\n'
        '    {% include "includes/page_header.html" with page_subtitle="People" page_title="Member Records" '
        'page_description="Baptism, marriage, transfers, and other spiritual records." '
        'action_url=add_url action_label="Add Record" %}',
    ),
    "templates/members/family_list.html": (
        r'<div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">\s*'
        r'<div>\s*<p class="page-subtitle mb-1">Members</p>\s*'
        r'<h1 class="page-title mb-0">Families</h1>\s*</div>\s*'
        r'<a href="{% url \'members:family_add\' %}" class="btn btn-primary btn-sm">Add Family</a>\s*</div>',
        '{% url \'members:family_add\' as add_url %}\n'
        '    {% include "includes/page_header.html" with page_subtitle="People" page_title="Families" '
        'action_url=add_url action_label="Add Family" %}',
    ),
    "templates/accounts/user_list.html": (
        r'<div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">\s*'
        r'<div>\s*<p class="page-subtitle mb-1">Administration</p>\s*'
        r'<h1 class="page-title mb-0">User Management</h1>\s*'
        r'<p class="page-description text-muted mb-0">Manage church staff accounts and roles\.</p>\s*'
        r'</div>\s*'
        r'<a href="{% url \'accounts:invite_user\' %}" class="btn btn-primary">\s*'
        r'<i class="bi bi-envelope-plus me-1"></i>Invite User\s*</a>\s*</div>',
        '{% url \'accounts:invite_user\' as invite_url %}\n'
        '    {% include "includes/page_header.html" with page_subtitle="Administration" page_title="User Management" '
        'page_description="Manage church staff accounts and roles." action_url=invite_url action_label="Invite User" %}',
    ),
    "templates/transactions/audit_log.html": (
        r'<div class="mb-4">\s*<p class="page-subtitle mb-1">Finance</p>\s*'
        r'<h1 class="page-title mb-0">Financial Audit Log</h1>\s*'
        r'<p class="page-description text-muted mb-0">Immutable record of financial actions\.</p>\s*</div>',
        '{% include "includes/page_header.html" with page_subtitle="Finance" page_title="Financial Audit Log" '
        'page_description="Immutable record of financial actions." %}',
    ),
    "templates/dashboard/notifications.html": (
        r'<div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">\s*'
        r'<div>\s*<p class="page-subtitle mb-1">Dashboard</p>\s*'
        r'<h1 class="page-title mb-0">Notifications</h1>\s*'
        r'{% if unread_count %}<p class="page-description text-muted mb-0 mt-1">{{ unread_count }} unread</p>{% endif %}\s*'
        r'</div>\s*'
        r'{% if unread_count %}\s*<form method="post" action="{% url \'dashboard:notification_mark_all_read\' %}">\s*'
        r'{% csrf_token %}\s*'
        r'<button type="submit" class="btn btn-outline-secondary btn-sm">Mark all read</button>\s*'
        r'</form>\s*{% endif %}\s*</div>',
        '{% include "includes/page_header.html" with page_subtitle="Dashboard" page_title="Notifications" %}\n'
        '    {% if unread_count %}\n'
        '    <p class="page-lead text-muted mb-3">{{ unread_count }} unread</p>\n'
        '    <form method="post" action="{% url \'dashboard:notification_mark_all_read\' %}" class="mb-3">\n'
        '        {% csrf_token %}\n'
        '        <button type="submit" class="btn btn-outline-secondary btn-sm">Mark all read</button>\n'
        '    </form>\n'
        '    {% endif %}',
    ),
}

LINK_FIXES = [
    (r'<td><strong>{{ dept\.name }}</strong></td>', r'<td><a href="{% url \'members:department_edit\' dept.pk %}" class="table-link">{{ dept.name }}</a></td>'),
    (r'<td>{{ t\.member }}</td>', r'<td><a href="{% url \'members:detail\' t.member_id %}" class="table-link">{{ t.member }}</a></td>'),
    (r'<td><a href="{% url \'members:detail\' record\.member_id %}">{{ record\.member }}</a></td>', r'<td><a href="{% url \'members:detail\' record.member_id %}" class="table-link">{{ record.member }}</a></td>'),
    (r'<td><a href="{% url \'members:record_detail\' record\.pk %}">{{ record\.title }}</a></td>', r'<td><a href="{% url \'members:record_detail\' record.pk %}" class="table-link">{{ record.title }}</a></td>'),
    (r'<td><a href="{% url \'members:family_detail\' family\.pk %}">{{ family\.name }}</a></td>', r'<td><a href="{% url \'members:family_detail\' family.pk %}" class="table-link">{{ family.name }}</a></td>'),
    (r'<td>{{ r\.member\.full_name }}</td>', r'<td><a href="{% url \'members:detail\' r.member_id %}" class="table-link">{{ r.member.full_name }}</a></td>'),
    (r'<td>{{ r\.bank_account\.name }}</td>', r'<td><a href="{% url \'transactions:reconciliation_detail\' r.pk %}" class="table-link">{{ r.bank_account.name }}</a></td>'),
    (r'class="table mb-0"', 'class="table table-hover mb-0"'),
]

FORM_FILES = [
    "templates/meetings/form.html",
    "templates/meetings/attendance_detail.html",
    "templates/members/spiritual_gift_form.html",
    "templates/members/assign_gift.html",
    "templates/members/baptism_register.html",
    "templates/organization/church_onboard.html",
    "templates/accounts/profile.html",
    "templates/accounts/invite_detail.html",
    "templates/accounts/accept_invite.html",
    "templates/accounts/invite_invalid.html",
]


def fix_detail_header(content, subtitle, title, description=None):
    desc_html = f'\n            <p class="text-muted mb-0">{description}</p>' if description else ""
    pattern = (
        r'<div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">\s*'
        r'<div>\s*<p class="page-subtitle mb-1">' + re.escape(subtitle) + r'</p>\s*'
        r'<h1 class="page-title mb-0">' + re.escape(title) + r'</h1>'
    )
    if description:
        pattern += r'(?:\s*<p class="[^"]*mb-0[^"]*">' + re.escape(description) + r'</p>)?'
    pattern += r'\s*</div>.*?</div>'
    desc_attr = f' page_description="{description}"' if description else ""
    repl = f'{{% include "includes/page_header.html" with page_subtitle="{subtitle}" page_title="{title}"{desc_attr} %}}'
    return re.sub(pattern, repl, content, count=1, flags=re.DOTALL)


def wrap_simple_form(content):
    if '<div class="form-card">' in content:
        return content
    if '<div class="row justify-content-center">' not in content:
        content = (
            '<div class="page-container">\n'
            '    <div class="row justify-content-center">\n'
            '        <div class="col-lg-8">\n'
            + content.split('<div class="page-container">', 1)[-1].split('{% endblock %}', 1)[0].strip()
            + '\n        </div>\n    </div>\n</div>'
        )
    content = re.sub(
        r'(<div class="col-lg-[78]">\s*)<div class="card">',
        r'\1<div class="form-card"><div class="card">',
        content,
        count=1,
    )
    if '<div class="form-card">' in content and content.count('</div>') > 0:
        content = re.sub(
            r'(</div>\s*</div>\s*)(</div>\s*</div>\s*</div>\s*{% endblock %})',
            r'\1            </div>\n        \2',
            content,
            count=1,
        )
    return content


def process(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel in SKIP:
        return False
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    orig = text

    if rel in REPLACEMENTS:
        pat, rep = REPLACEMENTS[rel]
        text = re.sub(pat, rep, text, flags=re.DOTALL)

    for pat, rep in LINK_FIXES:
        text = re.sub(pat, rep, text)

    if rel == "templates/members/detail.html":
        text = fix_detail_header(text, "People", "{{ member.full_name }}", "{{ member.church.name }}")
        text = re.sub(
            r'<a href="{% url \'members:family_detail\' member\.family_id %}">',
            r'<a href="{% url \'members:family_detail\' member.family_id %}" class="table-link">',
            text,
        )
    elif rel == "templates/transactions/transaction_detail.html":
        text = re.sub(
            r'<nav aria-label="breadcrumb" class="mb-3">.*?</nav>\s*'
            r'<div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">.*?</div>',
            '{% include "includes/page_header.html" with page_subtitle=transaction.transaction_type page_title=transaction.reference page_description=transaction.church.name %}',
            text,
            count=1,
            flags=re.DOTALL,
        )
    elif rel == "templates/meetings/detail.html":
        text = fix_detail_header(text, "Operations", "{{ meeting.title }}", "{{ meeting.scheduled_at|date:\"F j, Y g:i A\" }}")
    elif rel == "templates/transactions/reconciliation_detail.html":
        text = re.sub(
            r'<nav aria-label="breadcrumb" class="mb-3">.*?</nav>\s*'
            r'<div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">.*?</div>',
            '{% include "includes/page_header.html" with page_subtitle="Finance" page_title=reconciliation.bank_account.name page_description=reconciliation.statement_date %}',
            text,
            count=1,
            flags=re.DOTALL,
        )
        text = re.sub(
            r'<div class="row g-3 mb-4">\s*'
            r'(<div class="col-md-4"><div class="card text-center"><div class="card-body py-3">.*?</div></div></div>\s*){3}'
            r'</div>',
            lambda m: metrics_from_recon(m.group(0)),
            text,
            flags=re.DOTALL,
        )
    elif rel == "templates/transactions/period_list.html":
        text = fix_detail_header(text, "Finance", "Financial Period Lock", "{{ church.name }} — {{ year }}")
    elif rel == "templates/transactions/budget_report.html":
        text = re.sub(
            r'<div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">.*?</div>',
            '{% include "includes/page_header.html" with page_subtitle="Finance" page_title="Budget vs Actual" %}',
            text,
            count=1,
            flags=re.DOTALL,
        )
        text = re.sub(
            r'<form method="get" class="d-flex gap-2 align-items-center">',
            r'<div class="filter-bar"><form method="get" class="d-flex gap-2 align-items-center">',
            text,
        )
        text = re.sub(
            r'(<button type="submit" class="btn btn-sm btn-primary">Apply</button>\s*</form>)',
            r'\1</div>',
            text,
        )
    elif rel.endswith("_detail.html") and "page-subtitle" in text:
        # org detail pages - generic fix
        text = re.sub(
            r'<div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4">\s*'
            r'<div>\s*<p class="page-subtitle mb-1">([^<]+)</p>\s*'
            r'<h1 class="page-title mb-0">([^<]+)</h1>.*?</div>.*?</div>',
            r'{% include "includes/page_header.html" with page_subtitle="\1" page_title="\2" %}',
            text,
            count=1,
            flags=re.DOTALL,
        )

    if rel in FORM_FILES:
        text = wrap_simple_form(text)

    if rel == "templates/accounts/user_list.html":
        text = re.sub(
            r'<div class="card mb-4">\s*<div class="card-body">\s*(<form method="get".*?</form>)\s*</div>\s*</div>',
            r'<div class="filter-bar">\n        \1\n    </div>',
            text,
            flags=re.DOTALL,
        )
        text = re.sub(
            r'<strong>{{ u\.get_full_name\|default:u\.username }}</strong>',
            r'<a href="{% url \'accounts:user_detail\' u.pk %}" class="table-link">{{ u.get_full_name|default:u.username }}</a>',
            text,
        )

    if rel == "templates/budgets/list.html":
        text = re.sub(
            r'<div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">\s*'
            r'(<form method="get".*?</form>)\s*'
            r'(<a href="{% url \'budgets:create\' %}"[^>]*>.*?</a>)\s*</div>',
            r'<div class="filter-bar">\1</div>\n    <div class="d-flex justify-content-end mb-3">\2</div>',
            text,
            flags=re.DOTALL,
        )
        text = re.sub(
            r'<div class="card mb-4">\s*<div class="card-header">Budget vs Actual',
            r'<div class="data-card mb-4"><div class="data-card__header">Budget vs Actual',
            text,
        )
        text = re.sub(
            r'<div class="card">\s*<div class="card-header">Budget Lines',
            r'<div class="data-card"><div class="data-card__header">Budget Lines',
            text,
        )
        text = re.sub(r'<td>{{ row\.account }}</td>', r'<td class="table-link">{{ row.account }}</td>', text)
        text = re.sub(r'<td>{{ b\.account\.name }}</td>', r'<td><a href="{% url \'budgets:edit\' b.pk %}" class="table-link">{{ b.account.name }}</a></td>', text)

    if rel == "templates/giving/statement.html":
        text = re.sub(
            r'<h1 class="page-title h4">{{ member\.full_name }}</h1>\s*'
            r'<p class="text-muted">Giving statement — {{ year }}</p>',
            '{% include "includes/page_header.html" with page_subtitle="Finance" page_title=member.full_name page_description=giving_statement_desc %}',
            text,
        )
        # Fix - use static description
        text = text.replace(
            'page_description=giving_statement_desc %}',
            'page_description="Giving statement" %}',
        )
        text = re.sub(
            r'<p class="text-muted">Giving statement — {{ year }}</p>\s*',
            '<p class="page-lead text-muted">{{ year }}</p>\n    ',
            text,
        )

    if rel == "templates/organization/hierarchy.html":
        text = re.sub(
            r'<div class="row g-3 mb-4">\s*{% for label, value in stats\.items %}.*?{% endfor %}\s*</div>',
            '{% if stats %}\n    <div class="metrics-row">\n'
            '        {% for label, value in stats.items %}\n'
            '        <div class="metric-card"><span class="metric-label">{{ label|title }}</span>'
            '<span class="metric-value">{{ value }}</span></div>\n'
            '        {% endfor %}\n    </div>\n    {% endif %}',
            text,
            flags=re.DOTALL,
        )

    text = re.sub(r"\n{3,}", "\n\n", text)
    if text != orig:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def metrics_from_recon(block):
    labels = ["Statement Balance", "Matched Ledger Total", "Difference"]
    values = re.findall(r'<h4 class="mb-0[^"]*">([^<]+)</h4>', block)
    if len(values) != 3:
        return block
    lines = ['    <div class="metrics-row">']
    for i, (label, val) in enumerate(zip(labels, values)):
        extra = ' metric-card--success' if i == 2 and 'text-success' in block else (' metric-card--danger' if i == 2 else '')
        lines.append(f'        <div class="metric-card{extra}"><span class="metric-label">{label}</span><span class="metric-value">{val.strip()}</span></div>')
    lines.append('    </div>')
    return '\n'.join(lines)


def main():
    dirs = [
        "templates/transactions", "templates/members", "templates/announcements",
        "templates/meetings", "templates/reports", "templates/budgets",
        "templates/giving", "templates/organization", "templates/accounts", "templates/dashboard",
    ]
    updated = []
    for d in dirs:
        for p in sorted((ROOT / d).glob("*.html")):
            if process(p):
                updated.append(p.relative_to(ROOT).as_posix())
    print(f"Phase 3 updated {len(updated)} files:")
    for f in updated:
        print(f"  {f}")


if __name__ == "__main__":
    main()
