# OAuth + Authentication Methodology

## What You're Looking For

Flaws in how applications implement authentication and authorization flows — particularly OAuth 2.0, OpenID Connect, SSO, and session management. These bugs often result in account takeover, the highest-impact finding class.

---

## Mental Model

OAuth and SSO are complex multi-party flows. Bugs appear at the handoff points between parties:
- Between the user and the authorization server
- Between the authorization server and the application
- In how the application validates what it receives back

At each handoff, ask: **"What is this party trusting, and can I control that value?"**

---

## OAuth 2.0 Flow Testing

### Step 1 — Map the flow

Capture the full OAuth flow in Burp:
1. Initiate login → authorization request sent to OAuth server
2. User authenticates and consents
3. Authorization server redirects back with code or token
4. Application exchanges code for access token
5. Application uses token to fetch user info

Identify every parameter: `client_id`, `redirect_uri`, `state`, `scope`, `code`, `response_type`

### Step 2 — Test redirect_uri

This is the most commonly flawed parameter.

- **Open redirect:** Change `redirect_uri` to an external domain — does it redirect?
- **Path traversal:** `https://app.com/callback/../attacker`
- **Subdomain:** `https://attacker.app.com/callback`
- **Parameter pollution:** `redirect_uri=https://app.com/callback&redirect_uri=https://attacker.com`
- **Fragment:** `https://app.com/callback#https://attacker.com`

If the authorization code is sent to an attacker-controlled URI, account takeover is possible.

### Step 3 — Test state parameter

The `state` parameter prevents CSRF. If it is:
- Missing
- Not validated on callback
- Predictable/static

Then an attacker can initiate a login flow and trick a victim into completing it, linking the attacker's account to the victim's identity.

Test: Remove `state`, change it to a static value, replay an old state.

### Step 4 — Test token handling

- Is the authorization code single-use? Try replaying it.
- How long does the code remain valid? Test after 5, 10, 30 minutes.
- Is the access token stored in localStorage (XSS risk) or secure/httpOnly cookie?
- Can you use a token from one application with another application's client_id?

### Step 5 — Test scope manipulation

- Can you request scopes not intended for your client?
- Does the server silently grant extra scopes?
- Can you escalate from read to write scope?

---

## General Authentication Testing

### Password Reset Flow
- Does the reset link expire after use?
- Does it expire after a reasonable time period?
- Is the token in the URL or only in the email body?
- Can the token be guessed or brute-forced?
- Does changing password invalidate existing sessions?

### Session Management
- Does logout actually invalidate the server-side session?
- Do sessions expire after inactivity?
- Are session tokens long and random enough?
- Does the app accept old tokens after password change?

### Multi-Factor Authentication
- Can MFA be bypassed by directly accessing post-auth pages?
- Is the MFA code validated server-side?
- Is there a brute-force protection on MFA code entry?
- Can MFA be removed by an attacker with only a password?

### Account Linking / SSO
- Can an attacker link a victim's account to an attacker-controlled OAuth identity?
- Does the app verify email ownership when linking a social login?
- What happens when two accounts share the same email across providers?

---

## Common Patterns That Pay

| Pattern | Impact |
|---|---|
| redirect_uri not validated | Authorization code theft → ATO |
| state not validated | CSRF login → account linking ATO |
| Code replay accepted | ATO if attacker intercepts code |
| Password reset token in referrer | Token leakage → ATO |
| MFA bypass via direct URL access | Auth bypass |
| Logout doesn't invalidate session | Session persistence |
| Email not verified on account linking | ATO via provider confusion |
