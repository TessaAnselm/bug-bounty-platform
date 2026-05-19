# Step 6 — CI Pipeline (GitHub Actions)

## What We're Building

Automated security and quality checks on every push and pull request.

## Prerequisites

- Steps 1–5 complete and verified
- Repo pushed to GitHub (private)
- Snyk account connected (free tier)

## Files to Create

```
.github/
  workflows/
    ci.yml             main CI workflow
    security.yml       scheduled weekly deep scan
```

## ci.yml — Runs on Every Push

Four jobs, all must pass:

### Job 1: secrets-check (gitleaks)

Runs first — fastest check, most critical.

```yaml
- name: Run gitleaks
  uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Blocks merge if any secrets detected. Covers:
- API keys, tokens, passwords in code
- `.env` files accidentally staged
- Private keys in any format

### Job 2: static-analysis (Semgrep)

```yaml
- name: Run Semgrep
  uses: semgrep/semgrep-action@v1
  with:
    config: >-
      p/python
      p/security-audit
      p/secrets
      p/owasp-top-ten
```

Catches:
- SQL injection patterns
- Command injection in subprocess calls
- Hardcoded credentials
- Insecure deserialization
- OWASP Top 10 patterns in Python

### Job 3: dependency-scan (Snyk)

```yaml
- name: Run Snyk
  uses: snyk/actions/python@master
  env:
    SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
  with:
    command: test
    args: --severity-threshold=high
```

Catches:
- Known CVEs in Python dependencies
- License issues
- Supply chain risks

### Job 4: tests (pytest)

```yaml
- name: Run tests
  run: |
    pytest tests/ -v --tb=short
```

Runs:
- Unit tests for workflow activities (mocked DB)
- Schema validation tests
- MCP resource tests

## security.yml — Weekly Deep Scan

Runs on schedule `0 9 * * 1` (Monday 9am):

```yaml
- Snyk code scan (full, not just dependencies)
- Semgrep with extended ruleset
- Dependency audit (pip-audit)
- Generate SBOM (software bill of materials)
```

## Required GitHub Secrets

Set these in repo Settings → Secrets → Actions:

```
SNYK_TOKEN          from snyk.io account → settings → API token
```

## Branch Protection Rules

Set in repo Settings → Branches → main:

```
✅ Require status checks to pass before merging
   - secrets-check
   - static-analysis
   - dependency-scan
   - tests

✅ Require branches to be up to date before merging
✅ Do not allow bypassing the above settings
```

## Verification Gate

```bash
# 1. Push a clean commit — all jobs green
git push origin main
# Expected: all 4 CI jobs pass in GitHub Actions

# 2. Test secrets detection
# Create a temp branch, add a fake API key, push
git checkout -b test/secrets-check
echo "FAKE_KEY=sk-abc123secret" >> test_secret.txt
git add test_secret.txt && git commit -m "test"
git push origin test/secrets-check
# Expected: gitleaks job FAILS, blocks merge
# Clean up: git checkout main && git branch -D test/secrets-check

# 3. Snyk token works
# Expected: dependency-scan job shows "X known vulnerabilities"
#           or "No vulnerabilities found" — either is a passing result

# 4. Branch protection active
# Try to push directly to main without CI passing
# Expected: push rejected
```

## Notes

- All CI tools are free for public repos; Snyk free tier covers private repos up
  to 200 tests/month
- gitleaks runs in under 10 seconds — always the first job
- If Snyk finds vulnerabilities in dependencies: fix them before moving to
  Step 1 of building — CLAUDE.md policy requires this
- Add `# gitleaks:allow` inline comment only for known false positives
  (test fixtures, example values) — document why in a comment above
