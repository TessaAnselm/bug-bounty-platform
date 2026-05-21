# Ethics Commitments

This document formalizes the ethical commitments that govern every use of this platform.

---

## Core Principles

### 1. Authorization First
No recon, scanning, or testing begins without explicit authorization from the target organization through a recognized bug bounty program. Authorization is verified before a program is set to `active` in the platform.

### 2. Scope Respect
Testing is strictly limited to assets explicitly listed as in-scope by the program. Out-of-scope assets discovered during recon are stored but never tested. The platform enforces this technically via `validate_target()`.

### 3. Minimal Footprint
Recon is conducted with rate limiting and reasonable delays to avoid impacting production systems. No DoS, stress testing, or high-volume automated requests are made.

### 4. No Autonomous Exploitation
The platform orchestrates research workflows — it does not autonomously exploit vulnerabilities. Every potential finding requires human review before any follow-up action is taken.

### 5. Responsible Disclosure
All findings are reported through the program's official disclosure channel. No vulnerabilities are disclosed publicly before the program has had a reasonable opportunity to fix them.

### 6. Data Protection
Any sensitive data encountered during testing (credentials, PII, internal data) is:
- Not stored beyond what is needed for the finding report
- Reported immediately to the program
- Handled in accordance with the program's disclosure guidelines

### 7. No Harm
Testing stops immediately if there is any indication it is causing harm to the target's systems, users, or data.

---

## Pre-Engagement Checklist

Before any program is onboarded, the following must be verified:

- [ ] Program is active on a recognized platform (HackerOne, Bugcrowd, etc.)
- [ ] Terms of service have been read and accepted
- [ ] Scope has been reviewed and imported accurately
- [ ] Out-of-scope assets are explicitly listed
- [ ] Program allows automated recon tools (subfinder, httpx, etc.)
- [ ] Rate limits and testing windows have been noted
- [ ] Safe harbor clause is present in the program policy

This checklist is documented in `core/ethics-checklist.md`.

---

## What This Platform Is Not

- Not a penetration testing tool for hire
- Not a red team automation platform
- Not an autonomous AI hacking system
- Not authorized for use against any target outside a recognized bug bounty program

---

## Commitment

Every engagement conducted through this platform follows these ethics commitments without exception. If a situation arises where following these commitments conflicts with a potential finding, the commitments take priority.
