# OAuth + Authentication Checklist

## OAuth Flow Setup
- [ ] Full OAuth flow captured in Burp
- [ ] All parameters identified: client_id, redirect_uri, state, scope, code, response_type
- [ ] Flow type identified: Authorization Code, Implicit, PKCE, Client Credentials

## redirect_uri Tests
- [ ] External domain substitution attempted
- [ ] Path traversal attempted (`/callback/../attacker`)
- [ ] Subdomain variant attempted
- [ ] Parameter pollution attempted
- [ ] Partial match bypass attempted (if whitelist is prefix-based)

## state Parameter Tests
- [ ] State present in authorization request
- [ ] State validated on callback (remove it and see if flow completes)
- [ ] State value is unique per session (not static or predictable)
- [ ] Old/reused state values rejected

## Authorization Code Tests
- [ ] Code is single-use (replay after use → error)
- [ ] Code expiration tested (10 min, 30 min)
- [ ] Code cannot be used with different client_id

## Token Tests
- [ ] Access token storage location (localStorage vs httpOnly cookie)
- [ ] Token expiration enforced
- [ ] Refresh token rotation on use
- [ ] Scope in token matches requested scope

## Scope Tests
- [ ] Undocumented scopes tested
- [ ] Elevated scopes requested (admin, write, offline_access)
- [ ] Scope downgrade accepted (requesting less than granted)

## Password Reset
- [ ] Token expires after single use
- [ ] Token has reasonable expiry (< 1 hour)
- [ ] Token is not predictable
- [ ] Old sessions invalidated after reset

## Session Management
- [ ] Logout invalidates server-side session
- [ ] Session expires after inactivity
- [ ] Session rotated after login (fixation)
- [ ] Session invalidated after password change

## MFA
- [ ] MFA cannot be bypassed by direct URL navigation
- [ ] MFA code validated server-side
- [ ] Brute-force protection on MFA entry
- [ ] MFA removal requires re-authentication

## Account Linking
- [ ] Email verified before linking OAuth provider
- [ ] Attacker cannot link own provider to victim account
- [ ] Duplicate email across providers handled safely
