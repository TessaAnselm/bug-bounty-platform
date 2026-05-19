# IDOR + API Security Checklist

Run through this for every target. Check off as you test each item.

## Setup
- [ ] Two test accounts created (attacker + victim)
- [ ] Burp Suite proxy capturing all traffic
- [ ] All in-scope endpoints inventoried

## Object Reference Discovery
- [ ] IDs in URL path segments identified and listed
- [ ] IDs in query parameters identified and listed
- [ ] IDs in request body (JSON/form) identified and listed
- [ ] IDs in custom headers identified and listed
- [ ] Encoded/hashed references decoded and listed

## Horizontal IDOR Tests
- [ ] URL path IDs substituted with victim's object IDs
- [ ] Query parameter IDs substituted
- [ ] Body parameter IDs substituted
- [ ] Custom header IDs substituted
- [ ] Filenames in download/export endpoints substituted
- [ ] Email-based lookups tested with victim email
- [ ] Tested across GET, POST, PUT, PATCH, DELETE

## Vertical IDOR / Privilege Escalation
- [ ] Admin endpoints tested with regular user session
- [ ] Privileged actions tested with lower-privilege account
- [ ] Role parameter in body tested for manipulation (`role=admin`)
- [ ] Hidden UI elements accessed directly via API

## API-Specific Tests
- [ ] Unauthenticated access tested on all endpoints
- [ ] Expired/invalid tokens tested (do they fail gracefully?)
- [ ] Response fields reviewed for excessive data exposure
- [ ] Mass assignment tested (extra fields in POST/PUT body)
- [ ] API versioning checked (v1 vs v2 — older versions often less hardened)
- [ ] GraphQL introspection tested if applicable
- [ ] Rate limiting tested on sensitive endpoints (login, password reset, OTP)

## Error Response Analysis
- [ ] 403 vs 404 behavior noted (existence oracle)
- [ ] Error messages reviewed for information leakage
- [ ] Stack traces or internal paths in error responses noted
