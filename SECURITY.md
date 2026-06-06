# Security Policy

## Platform Purpose

This is a personal ethical security research platform built for authorized bug bounty hunting. It is designed as a research notebook and orchestration layer — not an autonomous exploitation engine.

---

## Safety Architecture

### What this platform does
- Passive recon: subdomain enumeration, HTTP probing, technology fingerprinting
- Asset discovery and change detection
- Finding lifecycle tracking (draft → submitted → resolved → paid)
- AI-assisted triage and note-taking (read-only, no write access to live systems)

### What this platform does NOT do
- Autonomous exploitation
- Payload injection without human approval
- Scanning targets outside the authorized scope
- Storing or transmitting credentials or sensitive data found during recon

---

## Human-in-the-Loop Design

Every action that touches a live target requires human approval:

1. **Ethics checklist** — must be completed and signed off before a program is set to `active`
2. **Program status gate** — recon workflows refuse to start if program status is not `active`
3. **Scope validation** — every discovered asset is validated against the program's defined scope before storage; out-of-scope assets are rejected and logged
4. **Finding workflow signals** — status transitions (submit, triage, resolve) require explicit human action via the dashboard
5. **Nuclei scanning** — disabled by default; must be explicitly enabled per program and requires manual trigger

---

## Scope Enforcement

Scope is enforced technically, not just by policy:

- Each program stores an explicit `scope` and `out_of_scope` list
- The `validate_target()` function checks every discovered asset against both lists before it is stored
- Assets that fail scope validation are silently dropped and logged — they are never stored or acted upon
- Wildcard and exact domain matching is supported

---

## Dashboard Authentication

The dashboard is protected by a single high-entropy API key, but the key itself
is never carried around the app — a session-token model isolates it:

- **Hash at rest** — only the SHA-256 hash of the key is stored (`DASHBOARD_API_KEY` in `.env`); the plaintext is never persisted. Empty/unset hash fails closed (the dashboard is locked, never open).
- **Signed session tokens** — at login the key is verified once, then the server issues an HMAC-SHA256-signed, 7-day-expiring token (`src/api/auth.py`). The `bounty_session` cookie holds the token, **not** the key. A stolen cookie expires and is not the master key. Tokens are stateless, so they survive a restart without a session store.
- **No credential in URLs/logs/history** — page links and forms carry nothing sensitive; the cookie travels automatically on same-origin requests. This removes the earlier pattern where the raw key was appended to every link and written into access logs.
- **Constant-time comparison** — key and token checks use `hmac.compare_digest` (no timing oracle).
- **Cookie flags** — `HttpOnly` (no JS access) and `SameSite=Strict` (no cross-site sends). Set `COOKIE_SECURE=true` to add the `Secure` flag once served over HTTPS.
- **Programmatic access** — curl/scripts authenticate per request with the raw key via `X-API-Key` header or `?api_key=` query param.
- **Loopback only** — the dashboard binds to `127.0.0.1`; it is not reachable from the network.

## Secrets Management

- All credentials live in `.env` (gitignored — never committed)
- `.env.example` provides a template with no real values
- No secrets are logged or stored in Temporal workflow history
- Database connection strings are never hardcoded

---

## Responsible Disclosure

If you discover a vulnerability in this platform itself:

1. Do not open a public GitHub issue
2. Email the maintainer directly
3. Allow reasonable time for a fix before any public disclosure

---

## Authorized Use Only

This platform is built exclusively for:
- Authorized bug bounty programs on HackerOne, Bugcrowd, or equivalent platforms
- Programs where the researcher has accepted the program's terms of service
- Targets explicitly listed in the program's in-scope assets

Any use against unauthorized targets is a violation of computer fraud laws and the terms of service of bug bounty platforms. The maintainer takes no responsibility for unauthorized use.
