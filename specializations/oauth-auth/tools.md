# OAuth + Authentication Tools

## Core Tools

### Burp Suite Community
Essential for capturing and manipulating OAuth flows.
- Use Repeater to modify individual parameters
- Use Intruder for token brute-force testing (within program scope)
- Install Logger++ extension for better traffic review

### Burp OAuth Scanner Extension
Automated checks for common OAuth misconfigurations.
- Available in BApp Store
- Supplements manual testing — do not rely on it exclusively

## JWT Testing

### jwt.io
Decode and inspect JWT tokens in the browser.
- https://jwt.io

### jwt_tool
Full JWT attack toolkit: algorithm confusion, key confusion, brute-force.
```bash
# Decode and analyze
python3 jwt_tool.py <token>

# Test algorithm confusion (RS256 → HS256)
python3 jwt_tool.py <token> -X a

# Test none algorithm
python3 jwt_tool.py <token> -X n
```

### hashcat
Brute-force weak HMAC secrets on HS256-signed JWTs.
```bash
hashcat -a 0 -m 16500 <jwt> wordlist.txt
```

## Session Analysis

### Cookie-Editor (browser extension)
Inspect and modify cookies without Burp for quick checks.

### EditThisCookie (browser extension)
Manipulate session cookies directly in the browser.

## PKCE / OAuth Specific

### oauth-scan (various)
Search GitHub for community-maintained OAuth testing scripts.
Manual testing with Burp is more reliable for most cases.

## Password Reset Token Analysis

### Burp Sequencer
Analyze randomness quality of tokens and session IDs.
- Capture token generation requests
- Run statistical analysis on the token space

## Reference

- OAuth 2.0 Security Best Current Practice: https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics
- OpenID Connect spec: https://openid.net/connect/
