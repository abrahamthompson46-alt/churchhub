# ChurchHub Version

| Field | Value |
|-------|-------|
| **Version** | `1.0.0` |
| **Codename** | General Availability |
| **Release date** | 22 July 2026 |
| **Status** | GA — production launch |
| **Python** | 3.13+ (CI); 3.14 supported with test harness notes |
| **Django** | `>=6.0.6` per `requirements.txt` |
| **Database** | PostgreSQL (production); SQLite (development) |
| **Prior candidate** | `2.0.0-rc1` (internal RC track — see `docs/RELEASE_NOTES_RC1.md`) |

## Versioning policy

ChurchHub follows [Semantic Versioning](https://semver.org/) from GA onward:

- **MAJOR** — breaking changes  
- **MINOR** — backward-compatible features  
- **PATCH** — backward-compatible fixes  

## Build metadata

| Item | Location |
|------|----------|
| Dependencies | `requirements.txt` |
| Migrations | Through `*_rc1_consistency` + `transactions.0019_financial_audit_immutability` |
| Settings | `church_system/settings/{development,staging,production}.py` |
| Release notes | `RELEASE_NOTES.md` |
| Changelog | `CHANGELOG.md` |
