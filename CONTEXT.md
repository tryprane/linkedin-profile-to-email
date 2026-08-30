# LinkedIn Profile to Email - AI Context & Engineering Reference

This document serves as the complete technical context, architecture blueprint, and constraints guide for any AI agent or developer continuing work on this codebase.

---

## 1. Project Overview & Objective

* **Project Name:** `linkedin-profile-to-email`
* **Actor ID (Apify):** `w2lIVylAXx0kv9i3E`
* **GitHub Repository:** [`https://github.com/tryprane/linkedin-profile-to-email`](https://github.com/tryprane/linkedin-profile-to-email)
* **Apify Console URL:** [`https://console.apify.com/actors/w2lIVylAXx0kv9i3E/runs`](https://console.apify.com/actors/w2lIVylAXx0kv9i3E/runs)

### Core Purpose:
An Apify Actor that takes a single LinkedIn profile URL, solves Cloudflare Turnstile challenges locally using **Scrapling (`StealthyFetcher`)**, queries the internal Mailmeteor lead-finder API with the minted Turnstile token, and outputs verified email address, full name, job title, and company metadata to the Apify dataset.

---

## 2. Mandatory Rules & Invariants (DO NOT VIOLATE)

1. **Scrapling is MANDATORY:**
   * Under **no circumstances** should `scrapling` (`StealthyFetcher`) be removed, swapped for plain Playwright, or replaced with third-party captcha APIs (like 2Captcha/CapSolver).
   * Scrapling is strictly mandated by the owner for local, automated Turnstile solving.
2. **Single LinkedIn URL Input Only:**
   * Do **NOT** add multi-URL batching arrays to the input schema. The actor expects a single string `linkedin_url` with strict normalization (handles vanity handles, protocol-less URLs, trailing slashes, and rejects invalid company/group URLs).
3. **Apify Residential Proxy Routing:**
   * The actor supports running Turnstile challenges and API calls through Apify Residential Proxies (`RESIDENTIAL`) or custom proxy URLs (`http://user:pass@host:port`).

---

## 3. Architecture & Mechanics

### How Turnstile Solving Works Locally:
1. **Embedded HTTPS Server ([`src/solver.py`](file:///Users/prane/Desktop/CDing/APifyActor/linkedin_profile_to_email/src/solver.py)):**
   * Spins up a temporary Python `HTTPServer` on `127.0.0.1:8443` with a self-signed SSL certificate (`cert.pem` / `key.pem`) generated for domain `tools.mailmeteor.com`.
   * Serves [`src/page/index.html`](file:///Users/prane/Desktop/CDing/APifyActor/linkedin_profile_to_email/src/page/index.html), which loads the Cloudflare Turnstile widget with Mailmeteor's public sitekey (`0x4AAAAAAAi-w1-rXwO1qV7S`).
2. **Domain Origin & Proxy Routing in Chromium:**
   * Uses Chromium flag `--host-resolver-rules="MAP tools.mailmeteor.com 127.0.0.1:8443, EXCLUDE challenges.cloudflare.com"`:
     * Requests to `tools.mailmeteor.com` resolve locally to `127.0.0.1:8443` (giving the widget the correct origin).
     * Requests to `challenges.cloudflare.com` bypass the local mapping and route through the assigned residential proxy.
   * Uses `--proxy-bypass-list="127.0.0.1;localhost;tools.mailmeteor.com;tools.mailmeteor.com:8443"` to ensure loopback traffic is never sent to the proxy.
3. **Scrapling Execution Settings:**
   * **`network_idle=False`**: Critical! Turnstile maintains persistent background telemetry pings. Setting `network_idle=False` ensures Scrapling returns immediately once `solved_token` is retrieved rather than hanging for 30s.
   * **`google_search=False`**: Disables Scrapling's Google referer injection which conflicts with Turnstile origins.

---

## 4. Codebase Structure & Key Files

```
linkedin_profile_to_email/
├── .actor/
│   ├── actor.json           # Apify Actor metadata specification
│   └── input_schema.json    # Input schema (linkedin_url, proxyConfiguration)
├── src/
│   ├── __init__.py
│   ├── main.py              # Main Apify Actor entrypoint & API client
│   ├── solver.py            # TurnstileSolver & Scrapling StealthyFetcher logic
│   ├── cert.pem             # SSL Certificate for tools.mailmeteor.com
│   ├── key.pem              # Private key for local HTTPS server
│   └── page/
│       └── index.html       # HTML page rendering the Cloudflare Turnstile widget
├── Dockerfile               # Debian base with Playwright Chromium, xvfb, Scrapling
├── requirements.txt         # apify, scrapling, playwright, urllib3
└── CONTEXT.md               # This context file
```

### Core Files Breakdown:
* **[`src/main.py`](file:///Users/prane/Desktop/CDing/APifyActor/linkedin_profile_to_email/src/main.py):**
  * `validate_and_normalize_linkedin_url(url)`: Cleans and standardizes input (e.g. `satyanadella` ➔ `https://www.linkedin.com/in/satyanadella`).
  * Resolves proxy URLs from `Actor.create_proxy_configuration()`.
  * Calls `TurnstileSolver.solve(url, proxy_url)`.
  * Queries `https://tools.mailmeteor.com/api/email-finder/linkedin` with payload `{"linkedin_url": ..., "cf_turnstile_response": ...}`.
  * Pushes clean record + raw API response to the default dataset.
* **[`src/solver.py`](file:///Users/prane/Desktop/CDing/APifyActor/linkedin_profile_to_email/src/solver.py):**
  * `TurnstileSolver`: Manages embedded HTTPS server lifecycle and Scrapling `StealthyFetcher.fetch()`.

---

## 5. Billing & Cost Reference (Real Apify Metrics)

### Pricing Formula on Apify Platform:
$$\text{Total Cost} = \text{Compute Units (CU Cost)} + \text{Residential Proxy Bandwidth Cost} + \text{Dataset Writes}$$

1. **Compute Units ($0.20 / CU):**
   * $\text{CUs} = \frac{\text{Memory (4 GB)} \times \text{Duration (Seconds)}}{3600}$
   * Normal runtime: **~9 to 15 seconds** ➔ **`$0.0010 - $0.0025 USD`**.
   * Note: 4096 MB (4 GB) is required for Chromium stability in Docker. Lowering to 1024 MB starves Chromium and quadruples runtime (resulting in *higher* overall CU cost).
2. **Residential Proxy Bandwidth ($8.00 / GB):**
   * Full Proxy (Turnstile challenge + API call): Consumes **~650 KB** ➔ **`$0.0051 USD`**.
   * API-Only Proxy (Challenge direct + API proxied): Consumes **~10 KB** ➔ **`$0.00008 USD`**.
3. **Total Cost per Lead Lookup:**
   * **Full Residential Proxy (Challenge + API):** **`~$0.006 – $0.008 USD`** (~0.6¢ - 0.8¢).
   * **Hybrid Mode (Direct Challenge + Proxy API):** **`~$0.002 – $0.003 USD`** (~0.2¢ - 0.3¢).

---

## 6. How to Build & Test on Apify Cloud

To trigger a build and test run via the Python SDK:

```python
from apify_client import ApifyClient

client = ApifyClient("YOUR_APIFY_API_TOKEN")
actor_id = "w2lIVylAXx0kv9i3E"

# 1. Build latest git commit
build = client.actor(actor_id).build(version_number="0.0", tag="latest", use_cache=False)

# 2. Run Actor with Residential Proxy
run = client.actor(actor_id).call(
    run_input={
        "linkedin_url": "https://www.linkedin.com/in/satyanadella",
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"]
        }
    },
    memory_mbytes=4096
)

# 3. Fetch Output
dataset_items = client.dataset(run["defaultDatasetId"]).list_items().items
print(dataset_items)
```

---

## 7. Known Edge Cases & Troubleshooting

| Symptom | Root Cause | Solution |
| :--- | :--- | :--- |
| `Page.wait_for_function: Timeout exceeded` | Turnstile canvas rendering blocked (e.g. by `--blink-settings=imagesEnabled=false`). | Keep image and WebGL rendering enabled in Chromium flags. |
| Scrapling hangs for 30s before completing | `network_idle` is waiting for continuous Turnstile telemetry pings. | Ensure `"network_idle": False` is passed in `fetch_kwargs`. |
| HTTP 403 `captcha` on API request | Turnstile token was minted from an IP that does not match the API request IP (IP mismatch). | Ensure both Turnstile solver and `urllib` API request use the exact same proxy session / host resolver mapping. |
| Memory thrashing / slow container boot | Memory set too low (<2048 MB) causing Chromium GC thrashing. | Keep memory allocation at `4096 MB`. |
