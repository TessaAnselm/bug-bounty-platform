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
