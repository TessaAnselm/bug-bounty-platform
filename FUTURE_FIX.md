# Future Fix — Improvement Proposal

Status: proposal for discussion. Nothing here has been implemented.

This document covers (1) housekeeping, (2) correctness / hygiene, and (3) the
design for a Burp-like MITM intercepting proxy built into the platform.

Guiding constraint from the project owner: **automation stays behind a human
gate.** Passive capture and observation are ungated; anything that sends,
modifies, replays, or fuzzes a live target is a deliberate human action or an
explicitly-permitted, rate-limited, scope-checked operation.

> **Accuracy note.** An earlier draft of this file listed several problems
> (missing `CODE_ARCHITECTURE.md`, single-migration "drift", untested scope /
> redaction boundaries) that turned out to be **false** — they came from a
> truncated file listing, not the real repository. Those were verified against
> the full tree and removed. What remains below has been checked against the
> actual code. See "Verified: not actually problems" at the end.

---

## 1. Housekeeping

Low-risk cleanups. None change behavior.

### 1.1 Keep `CLAUDE.md` current with `PROGRESS.md`
`CLAUDE.md` auto-loads at the start of every session, so anything stale there is
paid for on every run. Its "V1 Build Status" section still frames the project as
"6 steps + safety hardening, ready to hunt" and doesn't mention the hunter
decision layer that `PROGRESS.md` already records and that exists in the code:
hunt sessions + checklist engine, the Repeater and `http_exchanges` store,
evidence attach, report export, risk scoring / triage, program constraints,
program discovery, and the outcome feedback loop. Bring the `CLAUDE.md` status /
architecture summary up to what `PROGRESS.md` and the tree already show.

### 1.2 Pin the Python version
There are `.cpython-312` **and** `.cpython-313` bytecode caches side by side under
`alembic/` and `src/db/` — meaning the app and/or migrations have been run under
two different interpreters. Pin one (a `.python-version` file, and/or
`python_requires` in `requirements.txt` or a `pyproject.toml`) so the worker,
dashboard, and Alembic all run under the same interpreter. Cheap insurance
against version-specific surprises.

### 1.3 Document "secrets at rest"
Redaction (`redact_headers`, `redact_text` in `src/lib/compliance.py`) is applied
on every path that leaves the DB — the MCP exchanges resource
(`src/mcp/resources/exchanges.py`) and the report exporter both redact — which is
good. But the raw request/response bodies are still stored **un-redacted** in
`http_exchanges`, by necessity (you need the real evidence for a report). That's
a reasonable design choice; it's just currently undocumented. Add a short
"Evidence storage & secrets at rest" note to `SECURITY.md` stating that the local
DB holds raw captured traffic and that redaction is a presentation-layer control,
not an at-rest one.

---

## 2. Correctness / Hygiene

`QA_TRACKER.md` is the living gap list and already tracks most of this well
(`25 passed`, with unchecked items honestly marked). This section only adds what
isn't already there and calls out the highest-value unchecked items to pull
forward. It is meant to complement `QA_TRACKER.md`, not duplicate it.

### 2.1 `nuclei` is advertised but not implemented (docs↔code mismatch)
`nuclei` appears in `README.md` (listed under "Active recon") and in the program
detail UI ("passive only — no katana / gowitness / nuclei") — but there is no
nuclei runner activity in `src/activities/recon/` (the recon activities are
`subdomain_enum`, `http_probe`, `tech_fingerprint`, `screenshot`, `js_crawl`,
`hist_urls`, `github_osint`). Note `COMMANDS.md` §8 correctly describes active
scanning as **katana/gowitness only** — so the docs already disagree with each
other. A reader of the README believes a capability exists that doesn't. Two
clean options:
- Remove the nuclei claims so docs match code, **or**
- Implement it as the gated active-scan hook described in §3.6 (preferred if you
  want the "runs attacks, gated" capability anyway).

### 2.2 Scope matching keeps the port — in-scope hosts with a port get dropped
`validate_target()` strips the scheme and path but **not** the port:
`https://api.example.com:8443/x` normalizes to `api.example.com:8443`, which
`fnmatch` will not match against a bare-host scope entry (`api.example.com` or
`*.example.com`). This fails *closed* (an in-scope asset is rejected, not a
bypass), so it's a correctness / coverage bug, not a safety hole — but it means
any asset surfaced with an explicit port silently vanishes. `QA_TRACKER.md`
already flags this as unchecked ("Scope matching handles ports predictably").
Fix: strip the port before matching (and add the test). Mixed-case is actually
handled in code (both sides are lowercased) but is likewise untested — worth a
one-line test to close the QA row.

### 2.3 Pull these unchecked QA items forward — they're code-real but untested
Two unchecked `QA_TRACKER.md` rows guard behavior that already exists in the code
but has no test, and both touch a **release blocker**. Testing them is cheap and
high-value:
- **"Active recon tools run only when `allow_active_scanning` is enabled."** The
  gate exists in `recon.py` (katana/gowitness/js_crawl are behind `allow_active`),
  and the matching release blocker is *"Active scanning runs without explicit
  program permission."* A regression here is a hunt-stopping incident; it should
  not rely on manual verification.
- **"Migrations upgrade cleanly from an empty database"** / round-trip. The chain
  is clean (see the verified section), but nothing tests that `upgrade head` on a
  fresh DB reproduces the live schema. This is the *responsible* version of the
  migration concern — not drift today, but no guard against it tomorrow.

### 2.4 (Optional, minor) Direct test for the MCP exchanges resource
The redaction *functions* are well tested, and the report path is tested, but
there's no test that calls `list_exchanges_for_session` / `_exchange_dict`
directly and asserts a stored token comes back masked. The code already redacts
correctly (`src/mcp/resources/exchanges.py`); this would pin the behavior so a
future refactor can't silently drop it. Fits under the unchecked `QA_TRACKER.md`
MCP section. Nice-to-have.

---

## 3. MITM Intercepting Proxy (Burp-like)

The goal: a built-in intercepting proxy that captures browser↔target traffic,
lets you inspect / modify / replay requests, and feeds everything into the
existing scope-checked, redacted, evidence → finding pipeline. The differentiator
versus running stock Burp or mitmproxy is exactly that integration: a flow
captured here is already scope-validated, redacted for AI review, and one click
from a finding.

### 3.1 Don't build TLS interception — wrap `mitmproxy`
`mitmproxy` is free, OSS, Python-native, and already solves the hard, dangerous
parts: on-the-fly certificate generation, HTTP/2, WebSockets, streaming. Building
raw TLS MITM in-house would be months of work and a security liability. Run
mitmproxy as a process driven by a **custom addon**; the addon is where all of
BountyOS's existing policy plugs in. The value we add is the integration, not the
interception.

### 3.2 The addon is the enforcement point
mitmproxy exposes per-flow hooks (`request`, `response`). In those hooks, reuse
the functions that already exist — no new policy engine:

- `validate_target(host, scope, oos)` — decides whether a flow is in-scope.
  Out-of-scope hosts pass through untouched and are **not stored**, so browsing an
  unrelated site while the proxy is on never lands in the DB.
- `is_blocked_host` / `resolve_public_ip` — keep the SSRF / private-address guard
  identical to the Repeater (blocks loopback, RFC1918, link-local incl. cloud
  metadata).
- `compliance_headers` / `min_send_interval` — enforce the program's required
  identifying header and rate cap on anything the proxy **replays**. Passive
  capture needs no throttle; active replay does.
- `redact_headers` / `redact_text` — already applied on the MCP path, so captured
  flows stay safe for Claude Code to read.

### 3.3 Storage: reuse `http_exchanges`
Captured flows become `HttpExchange` rows — the same table the Repeater already
writes to. Minimal model changes:
- Add a `source` column: `proxy` vs `repeater`.
- Make `hunt_session_id` nullable (passively-captured flows aren't tied to a
  session until the hunter promotes them).
- Optionally an `intercepted` / `modified` flag for flows edited in-flight.

Everything downstream — triage, "send to Repeater," attach-as-evidence, report
export with redacted request/response — then works on proxy traffic for free.
This is Burp's "Send to Repeater / Intruder," except the destination is your
finding pipeline.

### 3.4 Three tiers, and where the gate sits
This maps directly onto the "gated before automation" rule:

1. **Passive capture** (default on) — flows logged, nothing sent that the browser
   didn't already send. No gate: it's observation.
2. **Intercept** (Burp's Intercept tab) — pause an in-scope request, let the
   hunter edit and Forward or Drop it. Human-in-loop by definition.
3. **Active automation** (Intruder-like fuzzing, passive scanner, nuclei) — runs
   only on explicit human command, only when `allow_active_scanning` is on and
   the tool isn't listed in `prohibited_tools`, always rate-limited through
   `compliance.py`. This is the layer to keep gated; the architecture already has
   the gate (`programs.constraints` + the compliance layer).

### 3.5 Dashboard additions
- **Proxy view**: flow list filterable by host / status / method, with a
  request/response inspector. The Repeater's editor template and the dark
  terminal CSS already give most of this.
- **Intercept toggle**: on/off, with Forward / Drop / Edit controls when a request
  is held.
- **CA-cert page**: download the proxy's root CA plus browser-trust instructions.

### 3.6 Optional later, still gated: active scan hook
Once passive capture + intercept are solid, a nuclei runner (which also closes
§2.1) fits as tier-3 automation: take an in-scope captured flow or asset, run
nuclei with a constrained template set, rate-limited, only when the program
permits active scanning. Output lands as **candidate findings with evidence** in
triage — a human still confirms and submits. "Runs attacks" = it does the work;
the hunter still pulls the trigger.

### 3.7 Two honest caveats
- **The CA cert is the real trust boundary.** Installing the proxy's root CA in a
  browser lets it MITM *all* of that browser's HTTPS. The scope filter (§3.2) must
  decide what is *stored*, so non-target browsing stays out of the DB entirely.
  This deserves its own section in `SECURITY.md`, and ideally a dedicated browser
  profile used only for hunting.
- **Worth building over stock Burp / mitmproxy?** Yes — but only because of the
  scope-enforcement + evidence-pipeline + MCP-readable-flows integration. If it
  ends up used like a plain proxy, stock tools win. Keep the integration the point.

---

## Suggested Sequencing

`AGENTS.md` sets the rules of engagement for any of this work: preserve scope
enforcement, keep the dashboard local-only, keep MCP read-only, and **add tests
with (not after) changes to safety, auth, recon, reporting, or database
behavior.** The MITM proxy touches the first two directly, so it must land with
new `QA_TRACKER.md` rows and tests, not on top of manual checking.

1. **§2.2 scope-port fix + §2.3 the two code-real-but-untested QA items** —
   smallest, highest safety leverage; closes release-blocker-adjacent gaps.
2. **Housekeeping §1** — cheap, removes doc drift.
3. **MITM proxy tiers 1–2 (§3.1–3.5)** — passive capture + intercept, wired into
   `http_exchanges` and the finding pipeline, shipped with its own QA rows
   (scope-filtered capture, out-of-scope never stored, redaction on the flow
   view). The core of what was asked for.
4. **Resolve `nuclei` (§2.1) via the gated active-scan hook (§3.6)** — only after
   tiers 1–2 are proven, and only behind the existing permission gate.

---

## Verified: not actually problems

Checked against the full repository and confirmed fine — recorded so they don't
get "re-discovered" later:

- **`CODE_ARCHITECTURE.md` exists.** (An earlier draft wrongly called it missing.)
- **Alembic migrations are clean and linear** — 8 revisions, one per schema
  change, no gaps or branches:
  `05f7f4a9d5e6 (initial) → 57154eda7e38 (confidence_score) →
  daa9c8789856 (risk_score/tags/source_tool) → 7a0cbb0b12ca (hunt_sessions) →
  651e8677fdfc (report_fields) → a4f2e9c3b1d8 (constraints) →
  d2f4a6b8c0e1 (http_exchanges) → e7c1a9d3f5b2 (compliance_and_draft)`.
- **The scope boundary is tested at the storage path**, not just in isolation —
  `test_store_assets_rejects_out_of_scope_before_db_write` and
  `test_store_assets_rejects_everything_when_scope_is_empty`.
- **Redaction is tested** in `test_repeater` (`redact_headers` / `redact_text`),
  `test_repeater_send` (stored + displayed redacted), and `test_evidence_report`
  (redaction holds through the full report), and the MCP exchanges resource
  (`src/mcp/resources/exchanges.py`) redacts headers and body before AI review.

_Nothing here is committed. This is a map for discussion._
