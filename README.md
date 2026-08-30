# LinkedIn Profile to Email Actor

An Apify Actor that accepts one LinkedIn profile URL, mints a Cloudflare Turnstile token with Scrapling, and queries Mailmeteor for the associated professional email.

## Cost-Optimized Architecture

The default path keeps the expensive Turnstile browser traffic on the container's direct connection and uses the configured residential proxy only for the small Mailmeteor API request. The browser page only creates a token; it never calls the email API itself.

- Default memory: 2048 MB
- Actor timeout: 60 seconds
- Scrapling navigation retries: 1
- Browser disk cache: disabled because Actor runs do not share it
- Mailmeteor lookups per run: exactly 1
- Raw API response duplication: omitted from output

If Mailmeteor rejects a token because the challenge and API request came from different IPs, set `proxyChallenge` to `true`. That compatibility mode routes both operations through the same proxy, but consumes substantially more residential bandwidth.

## Input

```json
{
  "linkedin_url": "https://www.linkedin.com/in/satyanadella",
  "proxyConfiguration": {
    "useApifyProxy": true,
    "apifyProxyGroups": ["RESIDENTIAL"]
  },
  "proxyChallenge": false
}
```

## Output

```json
{
  "linkedin_url": "https://www.linkedin.com/in/satyanadella",
  "found": true,
  "success": true,
  "email": "person@example.com",
  "validation": "valid",
  "job_title": "Job title",
  "company": "Company",
  "full_name": "Full Name",
  "api_proxy_used": true,
  "challenge_proxy_used": false,
  "api_transfer_bytes": 1024
}
```

## Local Verification

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
```
