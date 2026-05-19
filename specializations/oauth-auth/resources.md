# OAuth + Authentication Resources

## Must-Read

- **PortSwigger Web Academy — OAuth Authentication**
  https://portswigger.net/web-security/oauth
  The best structured introduction to OAuth attacks. Do every lab.

- **PortSwigger Web Academy — Authentication**
  https://portswigger.net/web-security/authentication
  Covers password attacks, MFA bypass, session flaws.

- **OAuth 2.0 Security Best Current Practice (IETF)**
  https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics
  The official security guidance from the OAuth working group.

## Foundational Reading

- **The OAuth 2.0 Authorization Framework (RFC 6749)**
  https://datatracker.ietf.org/doc/html/rfc6749
  Read sections 4 (grant types) and 10 (security considerations).

- **Attacking OAuth 2.0 Flows — PortSwigger Research**
  https://portswigger.net/research/hidden-oauth-attack-vectors

## Disclosed Reports (Study These)

Search HackerOne for OAuth disclosures:
https://hackerone.com/hacktivity?querystring=oauth

High-value disclosed reports to study:
- Account takeover via redirect_uri bypass
- CSRF via missing state parameter
- Token leakage via referrer header

## Books

- **Real-World Bug Hunting** — Peter Yaworski
  Chapter on authentication is practical and well-structured.

## Practice Labs

- **PortSwigger Web Academy** (free) — best for OAuth specifically
- **PentesterLab — JWT** exercises
- **HackTheBox** — machines with OAuth-based authentication paths

## Cheat Sheets

- **OAuth Attack Cheat Sheet** — https://github.com/daffainfo/AllAboutBugBounty/blob/master/OAuth%20Misconfiguration.md
- **JWT Attack Cheat Sheet** — https://github.com/swisskyrepo/PayloadsAllTheThings/tree/master/JSON%20Web%20Token
