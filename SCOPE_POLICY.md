# Scope Policy

This document describes how target scope is defined, validated, and enforced in this platform.

---

## How Scope Works

Every program stored in this platform has two scope fields:

| Field | Type | Description |
|---|---|---|
| `scope` | JSON array | Assets explicitly authorized for testing |
| `out_of_scope` | JSON array | Assets explicitly excluded from testing |

These are populated when a program is onboarded and must match the program's official scope definition on HackerOne, Bugcrowd, or equivalent.

---

## Scope Entry Formats

```
*.example.com          Wildcard — matches any subdomain of example.com
api.example.com        Exact — matches only api.example.com
example.com            Apex domain — matches example.com and all subdomains
192.168.1.0/24         CIDR range — matches IP addresses in range
https://example.com/*  URL pattern — matches paths under this URL
```

---

## Technical Enforcement

Scope is enforced by `validate_target()` in `src/activities/storage/scope.py`.

Every asset discovered during recon is validated before storage:

```
asset discovered by subfinder
        ↓
validate_target(asset, program.scope, program.out_of_scope)
        ↓
    in scope?  ──── NO ────→ asset dropped, logged, never stored
        │
       YES
        ↓
  asset stored in database
        ↓
  available for manual testing
```

Out-of-scope assets are never:
- Stored in the database
- Shown in the dashboard
- Tested in any follow-up activity
- Included in finding reports

---

## Scope Validation Rules

1. **Out-of-scope takes priority** — if an asset matches both scope and out_of_scope, it is rejected
2. **Wildcard matching** — `*.example.com` matches `api.example.com` but not `example.com` itself
3. **Apex matching** — `example.com` in scope matches the apex domain only unless wildcards are specified
4. **Case insensitive** — all domain matching is case insensitive
5. **Empty scope** — if a program has no scope defined, all recon is blocked until scope is added

---

## Scope Violations

If an out-of-scope asset is discovered to have been tested:

1. Stop all activity against that asset immediately
2. Document what was tested and when
3. Report the incident to the bug bounty program via their disclosure channel
4. Remove the asset from the database

---

## Adding or Updating Scope

Scope is set when a program is onboarded via `ProgramOnboardingWorkflow`. If the program updates its scope:

1. Update the program record in the database via the dashboard or directly via SQL
2. Re-run scope validation against existing stored assets
3. Remove any assets that are no longer in scope

Scope changes from the bug bounty platform take effect immediately and override any cached scope.

---

## Localhost / Demo Mode

When `DATABASE_URL` points to a local test database and no real program is active, the platform operates in a safe demo state — no recon tools are invoked and no external connections are made.
