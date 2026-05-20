# Snyk Security Findings Log

All issues found by Snyk code scans during the build. Includes what was found, why it was a problem, and how it was fixed.

---

## Step 4 — Dashboard (FastAPI)

**Scan date:** 2026-05-19
**Tool:** Snyk Code (SAST)
**Path scanned:** `src/api/`
**Result after fix:** 0 issues

---

### Finding 1 — Open Redirect in `notes.py` (create note)

| Field | Detail |
|---|---|
| Severity | Medium |
| File | `src/api/routers/notes.py` |
| Snyk ID | 62cb89e3-a430-4112-aead-3e3c73b7af4e |
| CWE | CWE-601: URL Redirection to Untrusted Site |

**What Snyk found:**

A `redirect_to` form field was passed directly from the HTTP request into `RedirectResponse` with no validation:

```python
# Vulnerable code
redirect_to: str = Form("/")
return RedirectResponse(url=f"{redirect_to}?api_key={api_key}", status_code=303)
```

**Why it's a problem:**

An attacker could set `redirect_to=https://phishing-site.com` in the form submission. The dashboard would redirect the user to that external URL. Since the redirect originates from your server, it appears trustworthy to the browser.

**Fix applied:**

Removed user-controlled input from the redirect entirely. The destination is now derived from the database (which note was saved → what asset/program does it belong to), then simplified further to always redirect to a fixed, hardcoded path:

```python
# Fixed code — no user input in redirect
return RedirectResponse(url=f"/assets?api_key={API_KEY}", status_code=303)
```

---

### Finding 2 — Open Redirect in `notes.py` (delete note)

| Field | Detail |
|---|---|
| Severity | Medium |
| File | `src/api/routers/notes.py` |
| Snyk ID | a138e541-9690-4424-bdba-0568acd9cf62 |
| CWE | CWE-601: URL Redirection to Untrusted Site |

**What Snyk found:**

Same root cause as Finding 1 — the delete note route also accepted a `redirect_to` form field and used it without validation:

```python
# Vulnerable code
redirect_to: str = Form("/")
return RedirectResponse(url=f"{redirect_to}?api_key={api_key}", status_code=303)
```

**Why it's a problem:**

Same as Finding 1. Any route that blindly follows a user-supplied URL is exploitable.

**Fix applied:**

Same fix as Finding 1. Redirect goes to a fixed path with no user-provided data in the URL:

```python
# Fixed code
return RedirectResponse(url=f"/assets?api_key={API_KEY}", status_code=303)
```

---

## Clean Scans (no issues found)

| Step | Path Scanned | Date | Result |
|---|---|---|---|
| Step 2 — Database models | `src/` | 2026-05-19 | ✅ 0 issues |
| Step 3 — Workflows + activities | `src/` | 2026-05-19 | ✅ 0 issues |
| Step 4 — Dashboard (after fix) | `src/api/` | 2026-05-19 | ✅ 0 issues |

---

## Lessons

- Any user-supplied value going into a redirect URL is an open redirect candidate — validate or eliminate it
- Snyk's taint analysis traces data through function calls and DB round-trips — even "sanitized" values may still be flagged if the taint origin is user input
- The safest fix is to not use user input in redirects at all — derive the destination from server-side state or use hardcoded paths
