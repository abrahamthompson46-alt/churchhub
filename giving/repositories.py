"""
Persistence helpers for the giving portal.

Giving is a read-only reporting/statement layer. It does not create, approve,
or void journals. The transactions app remains the accounting system of record.

This module intentionally has no write helpers. Do not add journal persistence
here — use transactions (and ledger posting templates) instead.
"""
