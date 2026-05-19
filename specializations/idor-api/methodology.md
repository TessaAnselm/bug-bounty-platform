# IDOR + API Security Methodology

## What You're Looking For

**IDOR (Insecure Direct Object Reference):** The application exposes a reference to an internal object (ID, filename, account number) and fails to verify the requesting user is authorized to access it.

**API Security:** Broken authorization, excessive data exposure, mass assignment, lack of rate limiting, and unauthenticated endpoints that should require auth.

These two overlap heavily — most IDOR bugs live in API endpoints.

---

## Mental Model

Every time you see an ID in a request, ask:
> "What happens if I change this to someone else's ID?"

Every time you see data returned in a response, ask:
> "Should this user be able to see all of this?"

Every time you create an object as User A, ask:
> "Can User B access, modify, or delete it?"

---

## Testing Process

### Phase 1 — Inventory all object references

While using the app normally (proxied through Burp), catalog:
- Every ID that appears in URLs, request bodies, or headers
- IDs that look sequential, UUIDs, hashed values, encoded strings
- Any endpoint that takes an ID as a parameter

### Phase 2 — Set up two test accounts

- Account A: attacker (your main session)
- Account B: victim (create objects here)

Never test IDOR against real user data. Always use your own test accounts.

### Phase 3 — Test horizontal IDOR

With Account A's session, attempt to access objects created by Account B:
- Direct URL substitution: change `/api/users/B_ID/profile` → `/api/users/A_ID/profile` (as A) but access B's data
- Body parameter substitution: change `{"user_id": "A"}` → `{"user_id": "B"}`
- Header substitution: some apps use `X-User-ID` headers that aren't validated

### Phase 4 — Test vertical IDOR (privilege escalation)

- Can a regular user access admin endpoints?
- Can a user perform actions reserved for higher privilege roles?
- Does the app rely only on UI to hide admin functions, not server-side checks?

### Phase 5 — Test indirect references

Not all references are obvious IDs:
- Filenames in download endpoints
- Email addresses as lookup keys
- Order numbers, invoice numbers, ticket IDs
- Encoded or hashed IDs (decode them, then test)

### Phase 6 — Test across HTTP methods

An endpoint that checks auth on GET may not check it on PUT, DELETE, or PATCH.
Test every method the endpoint accepts.

### Phase 7 — Check API response verbosity

Even if you can't access an object, does the error response leak information?
Does a 200 with empty data vs 403 reveal object existence?
Does the response include fields the user shouldn't see?

---

## Common Patterns That Pay

| Pattern | Example |
|---|---|
| Sequential IDs | `/api/orders/1001` → try `1000`, `999` |
| UUID in body, not validated | `{"invoice_id": "victim_uuid"}` |
| Mass assignment | POST body accepts `role=admin` |
| Indirect reference via email | `/api/export?email=victim@example.com` |
| Function-level auth bypass | Regular user hits `/api/admin/users` |
| State-changing via method switch | GET is protected, DELETE is not |
| Response includes hidden fields | API returns `password_hash`, `internal_notes` |
