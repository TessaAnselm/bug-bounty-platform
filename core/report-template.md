# Report Template

Use this structure for every submission. Adapt wording to the program's style, but never omit sections.

---

## Title

Format: `[Vulnerability Type] in [Feature/Endpoint] allows [Impact]`

Examples:
- `IDOR in /api/v1/invoices/{id} allows unauthenticated access to any user's billing records`
- `OAuth state parameter not validated in SSO flow allows account takeover`
- `Prompt injection in AI assistant exposes system prompt and internal tool definitions`

---

## Severity

State your assessed severity and the primary reason:

`High — unauthenticated attacker can read any user's private data at scale`

Use CVSS 3.1 score if the program requires it, but always include a plain-language explanation.

---

## Summary

2-3 sentences. What is vulnerable, what can an attacker do, why does it matter.

> The `/api/v1/documents/{id}` endpoint returns document contents based on the ID in the URL without verifying that the authenticated user owns that document. An attacker with a valid session can enumerate document IDs to read any other user's private documents. This exposes all user-uploaded content regardless of account ownership.

---

## Vulnerability Details

Explain the technical root cause clearly.

- What assumption the application is making
- What check is missing or bypassable
- Why this is exploitable

---

## Steps to Reproduce

Numbered, exact steps. Assume the triager has never used this app.

1. Create two accounts: `attacker@test.com` and `victim@test.com`
2. Log in as `victim@test.com` and upload a document. Note the document ID from the URL: `doc_id=1234`
3. Log out and log in as `attacker@test.com`
4. Send the following request:
```
GET /api/v1/documents/1234 HTTP/1.1
Host: app.example.com
Authorization: Bearer <attacker_token>
```
5. Observe that the response contains the victim's document contents.

---

## Proof of Concept

Attach:
- Annotated screenshots showing the request and response
- Video walkthrough if the steps are complex
- Burp Suite exported request/response if applicable

Never include real user data in attachments — use test accounts only.

---

## Impact

Describe what a real attacker could do with this vulnerability.

- Who is affected (all users, specific roles, unauthenticated users)
- What data or functionality is exposed
- Whether it is exploitable at scale or requires specific conditions
- Whether it can be chained with other findings

> An attacker with any valid account can read all documents belonging to any other user by incrementing or brute-forcing document IDs. Given that IDs appear sequential, this could be automated to exfiltrate the entire document corpus. No special privileges required beyond a free account.

---

## Suggested Fix

Brief, specific. Shows you understand the root cause.

> Verify that the authenticated user's ID matches the `owner_id` field of the requested document before returning its contents. Apply this check server-side on every document retrieval endpoint.

---

## Additional Notes

Optional. Include if relevant:
- Related endpoints with the same pattern
- Similar findings you did not fully test
- References to CWE, OWASP, or prior disclosures that support your report
