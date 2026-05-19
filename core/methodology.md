# Core Methodology

The universal process applied to every target, regardless of specialization.

---

## Step 1 — Scope Review

**Goal:** Know exactly what you can and cannot touch before writing a single request.

- Read the full program policy
- Build a scope map: in-scope domains, endpoints, features, asset types
- Note explicitly out-of-scope items and hard boundaries
- Check for testing restrictions (no automated scanning, no load testing, etc.)
- Note payout ranges by severity — informs where to focus effort

Output: `targets/<program>/scope.md`

---

## Step 2 — Target Research

**Goal:** Understand the business before you understand the attack surface.

- What does this company do? What data do they hold?
- Who are their users? What workflows matter most to the business?
- What would a real attacker want? (credentials, PII, financial data, admin access)
- Read their blog, changelog, release notes, job postings (reveals tech stack)
- Check their public GitHub repos if available
- Look for recent feature launches — new code = new bugs

Output: `targets/<program>/target-research.md`

---

## Step 3 — Surface Mapping

**Goal:** Build a manual map of the attack surface within scope.

- Walk through the application as a real user — every feature, every role
- Identify authentication boundaries (what changes between logged-out, user, admin)
- List all API endpoints you encounter (use Burp to capture traffic)
- Note file uploads, exports, webhooks, third-party integrations, OAuth flows
- Find mobile app endpoints if in scope
- Check JS files for hidden endpoints and API keys

Output: `targets/<program>/surface-map.md`

---

## Step 4 — Hypothesis Formation

**Goal:** Generate specific, testable ideas before testing anything.

For each surface area, ask:
- What assumption is this feature making about the user?
- What happens if I break that assumption?
- What data flows through here and where could it leak?
- What authorization check needs to exist here — and is it actually there?

Write hypotheses explicitly: *"I think endpoint X may not verify ownership of resource Y because Z."*

Output: `targets/<program>/hypotheses.md`

---

## Step 5 — Controlled Testing

**Goal:** Test hypotheses methodically with minimal footprint.

- Use your own test accounts — never real users
- Test one hypothesis at a time
- Document every request/response that matters
- If you find something, stop escalating — capture proof of concept only
- If you accidentally touch out-of-scope, stop and note it immediately

Tools: Burp Suite, manual browser, specialization-specific tools

Output: `targets/<program>/session-notes/` (gitignored)

---

## Step 6 — Impact Assessment

**Goal:** Honestly assess what an attacker could do with this vulnerability.

Ask:
- What is the worst realistic outcome if this is exploited?
- Does it require authentication? What privilege level?
- Is it exploitable remotely, at scale, or only in specific conditions?
- Does it expose PII, credentials, financial data, or admin functionality?
- Can it be chained with another finding to escalate impact?

Use CVSS as a starting framework but describe impact in plain language in the report.

---

## Step 7 — Report Writing

**Goal:** Write a report that gets triaged fast and paid correctly.

See [report-template.md](report-template.md) for structure.

Principles:
- Clear reproduction steps — assume the triager has never seen this app
- One vulnerability per report
- Honest severity — overstating gets you flagged, understating loses money
- Working PoC — video or annotated screenshots
- Suggested fix — shows expertise and speeds resolution

---

## Step 8 — Post-Submission

**Goal:** Close the loop and extract learning.

- Respond to triage questions promptly and professionally
- If severity is disputed, explain your reasoning calmly with evidence
- Once resolved, add the finding pattern to your specialization notes
- Ask yourself: what about this target or technique applies elsewhere?

---

## Phased Specialization

```
Phase 1 (active)      IDOR + API Security
Phase 2               OAuth + Authentication
Phase 3               AI/LLM Security
```

Each phase: get comfortable enough to find and report a paid bug before moving to the next.
