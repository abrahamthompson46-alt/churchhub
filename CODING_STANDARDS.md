# ChurchHub Enterprise
# CODING_STANDARDS.md

Version: 2.0

---

# Purpose

This document defines coding standards for ChurchHub Enterprise.

The objective is to maintain:

- Clean code
- Consistency
- Maintainability
- Security
- Readability
- Enterprise quality

All contributors and AI coding assistants must follow these standards.

---

# General Principles

Always write code that is:

- Simple
- Explicit
- Testable
- Maintainable
- Secure
- Performant

Prefer:

Readable code over clever code.

Clear names over short names.

Small functions over large functions.

Reusable components over duplication.

---

# Python Standards

Follow:

PEP 8

PEP 484 Type Hints

PEP 257 Docstrings

Black formatting

Ruff linting

---

# Python Version

Supported:

Python 3.13+

Code should remain compatible with future Python versions.

Avoid deprecated syntax.

---

# Naming Conventions

## Classes

Use PascalCase.

Examples:

```python
class MemberService:
    pass


class AttendanceReport:
    pass
```

---

## Functions

Use snake_case.

Examples:

```python
def calculate_member_age():
    pass


def generate_financial_report():
    pass
```

---

## Variables

Use descriptive names.

Good:

```python
member_count
approved_transactions
monthly_budget
```

Bad:

```python
x
data
temp
obj
```

---

# Constants

Use uppercase.

Example:

```python
MAX_LOGIN_ATTEMPTS = 5

DEFAULT_PAGE_SIZE = 25
```

---

# Imports

Organize imports:

1. Python standard library

2. Third-party packages

3. Django imports

4. Local applications

Example:

```python
import datetime

from decimal import Decimal

from django.db import transaction

from members.models import Member
```

Avoid wildcard imports.

Never use:

```python
from module import *
```

---

# Django App Structure

Preferred structure:

```
members/

    models.py

    admin.py

    apps.py

    services/

        member_service.py

    selectors/

        member_selector.py

    managers.py

    permissions.py

    validators.py

    forms.py

    views/

    api/

    reports/

    tests/

    migrations/
```

---

# Models

Models should contain:

- Fields
- Relationships
- Constraints
- Simple validation
- String representations

Avoid putting large workflows inside models.

---

# Model Example

Preferred:

```python
class Member(BaseModel):

    first_name = models.CharField(
        max_length=100
    )

    church = models.ForeignKey(
        Church,
        on_delete=models.PROTECT
    )

    def __str__(self):
        return self.full_name
```

---

# Model Rules

Every important model should have:

- Meaningful fields
- Database constraints
- Indexes where required
- Proper relationships
- Documentation

---

# Views

Views should be thin.

A view should:

1. Receive request

2. Validate permission

3. Call service

4. Return response

---

Avoid:

```python
def create_member(request):

    # 200 lines of business logic

```

---

Prefer:

```python
def create_member(request):

    member = MemberService.create(
        request.user,
        form.cleaned_data
    )

    return redirect(member)
```

---

# Services

Services contain business logic.

Examples:

```
MemberService

AttendanceService

FinanceService

BudgetService

PayrollService

AssetService
```

---

# Service Rules

Services should:

- Validate business rules
- Handle workflows
- Control transactions
- Trigger notifications
- Create audit logs

Services should not:

- Render templates
- Handle HTTP requests
- Contain HTML

---

# Selectors

Selectors handle complex reads.

Examples:

```
MemberSelector

DashboardSelector

FinancialReportSelector

AttendanceSelector
```

---

# Selector Rules

Selectors should:

- Return QuerySets or data objects
- Optimize queries
- Use select_related
- Use prefetch_related

Selectors should never:

- Modify database data
- Trigger side effects

---

# Managers

Managers contain reusable query behavior.

Example:

```python
class MemberQuerySet(models.QuerySet):

    def active(self):
        return self.filter(
            is_active=True
        )
```

---

# Forms

Forms should handle:

- User input
- Field validation
- Display concerns

Business rules belong in services.

---

# Templates

Templates must never contain:

- Database queries
- Permission logic
- Financial calculations
- Complex conditions

---

# JavaScript Standards

JavaScript should:

- Be modular
- Avoid duplicated code
- Handle errors gracefully
- Use meaningful names

Avoid:

Large scripts inside HTML templates.

---

# CSS Standards

Use:

Bootstrap utilities first.

Custom CSS only when necessary.

Avoid:

Duplicate styling.

Inline styles.

!important abuse.

---

# Error Handling

Never silently ignore exceptions.

Bad:

```python
try:
    process()
except:
    pass
```

---

Good:

```python
try:
    process()

except ValidationError as error:

    logger.warning(
        "Validation failed",
        exc_info=error
    )

    raise
```

---

# Logging Standards

Use structured logging.

Example:

```python
logger.info(
    "Member created",
    extra={
        "member_id": member.id
    }
)
```

Never log:

Passwords

Tokens

Sensitive personal information

---

# Type Hints

Use type hints for important functions.

Example:

```python
def calculate_balance(
    account_id: UUID
) -> Decimal:

    pass
```

---

# Documentation

Every complex function requires:

- Purpose
- Parameters
- Return value
- Exceptions

Example:

```python
def transfer_member():

    """
    Transfers a member between churches.

    Maintains transfer history
    and creates audit records.
    """
```

---

# Code Duplication

Never duplicate:

Validation

Calculations

Queries

Permission checks

Formatting logic

Create reusable services instead.

---

# Security Rules

Never:

Hardcode secrets.

Trust user input.

Skip validation.

Bypass permissions.

Expose sensitive information.

---

# Performance Rules

Avoid:

Queries inside loops.

Loading unnecessary objects.

Repeated calculations.

Prefer:

Caching

Aggregation

Bulk operations

Optimized queries

---

# Testing Standards

Every feature should include tests for:

Success case

Failure case

Permission case

Edge cases

Regression scenarios

---

# Final Coding Principle

Write code that another engineer can understand five years from now.

Clarity is more valuable than cleverness.

Maintainability is more valuable than speed.

Quality is a requirement, not an option.

# END OF CODING_STANDARDS.md