# LinkedIn Profile to Email - Engineering Context

## Purpose

This Apify Actor accepts one LinkedIn profile URL, mints a Mailmeteor-compatible Cloudflare Turnstile token with Scrapling, calls Mailmeteor's LinkedIn email-finder endpoint, and writes the normalized result to the default dataset and `OUTPUT` key-value record.

- Actor ID: `w2lIVylAXx0kv9i3E`
- Repository: `https://github.com/tryprane/linkedin-profile-to-email`
- Mailmeteor endpoint: `https://tools.mailmeteor.com/api/email-finder/linkedin`

## Invariants

1. Keep Scrapling `StealthyFetcher`; do not replace it with plain Playwright or a paid captcha service.
2. Keep a single `linkedin_url` string input. Do not add multi-URL batching.
3. Continue supporting Apify residential proxies and custom `PROXY_URL` values.
4. Keep images, canvas, and WebGL available to Turnstile.
5. Keep `network_idle=False`; Turnstile telemetry can otherwise delay browser shutdown.

## Current Architecture

1. `src/main.py` validates and normalizes the LinkedIn URL.
2. It creates one proxy URL for the Mailmeteor API request.
3. `src/solver.py` starts a temporary HTTPS server on `127.0.0.1:8443` using the certificate in `page/`.
4. Scrapling opens `https://tools.mailmeteor.com:8443`. Chromium maps that hostname to the local server while Cloudflare challenge requests go to the network.
5. `page/index.html` renders and immediately executes Turnstile. It only stores the resulting token; it does not call Mailmeteor.
6. Scrapling exits as soon as the token is available, and the local server shuts down with a short polling interval.
7. Python makes exactly one Mailmeteor request, then writes a compact normalized output.

## Proxy Modes

### Default: API-Only Proxy

`proxyChallenge=false` keeps the browser challenge direct and sends only the small API request through the configured proxy. This is the lowest-cost reliable default because residential challenge traffic is normally hundreds of kilobytes larger than the API request.

### Compatibility: Same Proxy for Challenge and API

Set `proxyChallenge=true` only when Mailmeteor returns a captcha/IP-mismatch response. This gives the challenge and API request the same proxy route, but materially increases residential bandwidth cost.

## Cost Controls

- Default Actor memory is 2048 MB rather than 4096 MB.
- Default timeout is 60 seconds.
- Turnstile solve timeout is 25 seconds.
- Scrapling retries are capped at one, preventing three expensive browser attempts on failed navigation.
- The browser disk cache was removed because ephemeral Actor runs cannot reuse it.
- The challenge page no longer starts a duplicate Mailmeteor API request.
- The request body contains only `linkedin_url`; the Turnstile token appears once in the query string.
- The raw API response is not nested into the normalized output, reducing storage bytes.
- `.dockerignore` excludes Git data, local caches, storage, bytecode, and the large HAR file from the image context.
- Unused direct dependencies were removed from `requirements.txt`; Scrapling owns its browser dependencies.

Apify compute is based on allocated memory multiplied by runtime. Relative to a 4096 MB run of the same duration, the 2048 MB default halves compute units. Actual runtime and success rate must still be measured on Apify because Turnstile behavior and container startup time vary.

## Important Tradeoff

Do not reduce memory to 1024 MB without an Apify benchmark. Chromium may become slower or unstable enough that the longer duration cancels the memory saving. Compare at least 10 successful runs per memory tier and optimize for `memory GB * duration hours`, not memory alone.

## Files

```text
.actor/actor.json          Actor metadata and 2048 MB / 60 s defaults
.actor/input_schema.json   Single URL, proxy configuration, proxyChallenge switch
Dockerfile                 Apify Playwright image plus Scrapling installation
page/cert.crt              Local HTTPS certificate
page/cert.key              Local HTTPS private key
page/index.html            Minimal token-only Turnstile page
src/main.py                Validation, proxy selection, one API request, output
src/solver.py              HTTPS server and Scrapling browser lifecycle
tests/                     Unit and architecture regression tests
```

## Verification

Run before deployment:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
python3 -m json.tool .actor/actor.json >/dev/null
python3 -m json.tool .actor/input_schema.json >/dev/null
```

The local sandbox may prohibit binding `127.0.0.1`, so the complete Turnstile flow must be verified in an Apify cloud run. Compare `proxyChallenge=false` and `true` only if the default mode receives an IP-mismatch/captcha response.
