# LinkedIn Profile to Verified Email Actor

Extract verified business email addresses, full name, job title, and company directly from any LinkedIn profile URL.

---

## ⚡ Key Features

- **Direct LinkedIn Email Extraction**: Find professional and verified emails from LinkedIn profile URLs.
- **Fast & Lightweight Execution**: Completes in ~3–6 seconds per lookup.
- **Automated Security Resolution**: Handles Cloudflare Turnstile token resolution seamlessly.
- **Enforced Apify Residential Proxy**: Guaranteed high delivery rates and unblocked requests.

---

## 📥 Input Specification

The Actor accepts a single verified LinkedIn profile URL:

```json
{
  "linkedin_url": "https://www.linkedin.com/in/satyanadella"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `linkedin_url` | String | **Yes** | Valid LinkedIn profile URL (e.g., `https://www.linkedin.com/in/username`). |

---

## 📤 Output / Dataset Format

```json
{
  "linkedin_url": "https://www.linkedin.com/in/satyanadella",
  "found": true,
  "success": true,
  "email": "satya@uchicago.edu",
  "validation": "valid",
  "job_title": "Member Board Of Trustees",
  "company": "University Of Chicago",
  "full_name": "Satya Nadella",
  "api_proxy_used": true,
  "api_transfer_bytes": 1420
}
```
