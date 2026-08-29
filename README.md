# LinkedIn Profile to Mail Actor

An Apify Actor to find professional email addresses from LinkedIn profile URLs with automated Cloudflare Turnstile token solving.

## 🚀 Features
- **High Success Rate:** Embedded local Turnstile solver that mints valid Cloudflare tokens on the fly.
- **Zero Proxy Waste for Solver:** Solves the challenge directly on the container interface without wasting residential proxy bandwidth on heavy challenge bytecode.
- **Apify Residential Proxy for API:** Routes the lightweight API lookup through Apify Residential Proxies to ensure clean, high-reputation requests.

## 📥 Input Example
```json
{
  "linkedin_url": "https://www.linkedin.com/in/satyanadella"
}
```

## 📤 Output Example
```json
{
  "linkedin_url": "https://www.linkedin.com/in/satyanadella",
  "found": true,
  "success": true,
  "email": "satya@uchicago.edu",
  "validation": "valid",
  "job_title": "Member Board Of Trustees",
  "company": "University Of Chicago",
  "full_name": "Satya Nadella"
}
```
