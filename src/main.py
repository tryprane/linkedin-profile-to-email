import asyncio
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from apify import Actor

from src.solver import TurnstileSolver

SERVICE_ENDPOINT = "https://tools.mailmeteor.com/api/email-finder/linkedin"
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT = 30


def validate_and_normalize_linkedin_url(url: str) -> tuple[bool, str, str]:
    """Validate and normalize a single LinkedIn profile URL."""
    if not url or not isinstance(url, str):
        return False, "", "The 'linkedin_url' input parameter is required."

    clean_url = url.strip()
    if clean_url.startswith(("www.linkedin.com", "linkedin.com")):
        clean_url = "https://" + clean_url
    elif not clean_url.startswith(("http://", "https://")):
        if "/" not in clean_url and not clean_url.startswith("http"):
            clean_url = f"https://www.linkedin.com/in/{clean_url}"
        else:
            clean_url = "https://" + clean_url

    linkedin_pattern = re.compile(
        r"^https?://(www\.)?linkedin\.com/in/([a-zA-Z0-9_-]+(?:%[0-9a-fA-F]{2})*)/?(\?.*)?$",
        re.IGNORECASE,
    )
    match = linkedin_pattern.match(clean_url)
    if not match:
        return (
            False,
            clean_url,
            "Invalid LinkedIn profile URL format. Expected: https://www.linkedin.com/in/username",
        )

    return True, f"https://www.linkedin.com/in/{match.group(2)}", ""


def build_api_request(linkedin_url: str, token: str) -> urllib.request.Request:
    """Build the single lightweight email lookup request."""
    api_url = f"{SERVICE_ENDPOINT}?{urlencode({'cf-turnstile-response': token})}"
    post_data = json.dumps(
        {"linkedin_url": linkedin_url},
        separators=(",", ":"),
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Origin": "https://mailmeteor.com",
        "Referer": "https://mailmeteor.com/",
        "Accept": "application/json",
    }
    return urllib.request.Request(api_url, data=post_data, headers=headers)


def query_email_api(
    linkedin_url: str,
    token: str,
    proxy_url: str | None,
    timeout: int = REQUEST_TIMEOUT,
) -> tuple[dict[str, Any], int, float]:
    request = build_api_request(linkedin_url, token)
    if proxy_url:
        proxy_handler = urllib.request.ProxyHandler(
            {"http": proxy_url, "https": proxy_url}
        )
        opener = urllib.request.build_opener(proxy_handler)
    else:
        opener = urllib.request.build_opener()

    started_at = time.monotonic()
    with opener.open(request, timeout=timeout) as response:
        response_bytes = response.read()

    result = json.loads(response_bytes.decode("utf-8"))
    transfer_bytes = len(request.data or b"") + len(response_bytes)
    return result, transfer_bytes, time.monotonic() - started_at


async def main():
    async with Actor:
        actor_input = await Actor.get_input() or {}
        raw_url = (
            actor_input.get("linkedin_url")
            or actor_input.get("linkedinUrl")
            or actor_input.get("url", "")
        )

        is_valid, linkedin_url, error_message = validate_and_normalize_linkedin_url(raw_url)
        if not is_valid:
            Actor.log.error(
                f"Input validation error: {error_message} (Received: '{raw_url}')"
            )
            await Actor.push_data(
                {
                    "linkedin_url": raw_url or None,
                    "found": False,
                    "email": None,
                    "full_name": None,
                    "job_title": None,
                    "company": None,
                    "validation": None,
                    "error": "invalid_input",
                    "message": error_message,
                }
            )
            await Actor.fail(status_message=error_message)
            return

        Actor.log.info(f"Starting Email Finder for: {linkedin_url}")

        # Initialize Apify Proxy Configuration
        proxy_configuration = None
        default_proxy_url = os.environ.get("PROXY_URL")
        try:
            proxy_configuration = await Actor.create_proxy_configuration(
                groups=["RESIDENTIAL"]
            )
            if proxy_configuration:
                Actor.log.info("Apify Residential Proxy initialized successfully.")
            elif not default_proxy_url:
                raise RuntimeError("Apify Proxy is mandatory for email extraction.")
        except Exception as error:
            if not default_proxy_url:
                Actor.log.error(f"Failed to initialize Apify Proxy: {error}")
                await Actor.fail(status_message="Apify Proxy configuration is required.")
                return

        # Solve Turnstile Token
        Actor.log.info("Resolving security verification challenge...")
        token = await asyncio.to_thread(
            TurnstileSolver().solve,
            proxy_url=None,
            timeout=25,
        )

        if not token:
            Actor.log.error("Failed to solve verification challenge.")
            await Actor.push_data(
                {
                    "linkedin_url": linkedin_url,
                    "found": False,
                    "email": None,
                    "full_name": None,
                    "job_title": None,
                    "company": None,
                    "validation": None,
                    "error": "turnstile_solve_failed",
                    "message": "Could not acquire a valid security token.",
                }
            )
            await Actor.fail(status_message="Security challenge solve failed.")
            return

        Actor.log.info("Security challenge resolved successfully.")

        # Execute Query with Retries & Session Rotation
        last_error = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            # Rotate proxy session ID on each attempt for clean residential IP
            current_proxy = default_proxy_url
            if proxy_configuration:
                session_id = f"session_{secrets.token_hex(4)}_{attempt}"
                current_proxy = await proxy_configuration.new_url(session_id=session_id)

            Actor.log.info(f"Executing email extraction request (Attempt {attempt}/{MAX_ATTEMPTS})...")
            try:
                result, transfer_bytes, latency = await asyncio.to_thread(
                    query_email_api,
                    linkedin_url,
                    token,
                    current_proxy,
                    timeout=REQUEST_TIMEOUT,
                )

                # Check if upstream returned rate-limit or captcha in JSON
                if result.get("error") and str(result.get("code", "")).lower() in ("rate_limit", "captcha"):
                    Actor.log.warning(
                        f"Upstream flagged session on attempt {attempt} ({result.get('code')}). Rotating session..."
                    )
                    last_error = result.get("message", "Upstream rate limited session")
                    if attempt < MAX_ATTEMPTS:
                        # Re-solve token if it was spent
                        if str(result.get("code", "")).lower() == "captcha":
                            token = await asyncio.to_thread(TurnstileSolver().solve, proxy_url=None, timeout=25) or token
                        await asyncio.sleep(1.5)
                        continue

                Actor.log.info(
                    f"Lookup completed in {latency:.2f}s ({transfer_bytes} body bytes transferred)."
                )

                is_found = bool(result.get("found") or result.get("email"))
                output = {
                    "linkedin_url": linkedin_url,
                    "found": is_found,
                    "email": result.get("email") if is_found else None,
                    "full_name": result.get("full_name"),
                    "job_title": result.get("job_title"),
                    "company": result.get("company"),
                    "validation": result.get("validation", "valid" if is_found else "unverified"),
                }
                Actor.log.info(
                    f"Result: Found={output['found']}, Email={output['email']}"
                )
                await Actor.push_data(output)
                return

            except urllib.error.HTTPError as error:
                error_body = error.read().decode("utf-8") if error.fp else ""
                Actor.log.warning(f"HTTP {error.code} on attempt {attempt}: {error_body}")
                last_error = f"HTTP {error.code}: {error_body}"
                if attempt < MAX_ATTEMPTS:
                    if error.code == 403:
                        token = await asyncio.to_thread(TurnstileSolver().solve, proxy_url=None, timeout=25) or token
                    await asyncio.sleep(2.0)
                    continue

            except (urllib.error.URLError, TimeoutError, OSError, Exception) as error:
                Actor.log.warning(f"Network error on attempt {attempt}: {error}")
                last_error = str(error)
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(1.5)
                    continue

        # If all attempts exhausted
        Actor.log.error(f"All extraction attempts failed: {last_error}")
        failure_output = {
            "linkedin_url": linkedin_url,
            "found": False,
            "email": None,
            "full_name": None,
            "job_title": None,
            "company": None,
            "validation": "unverified",
            "error": "extraction_failed",
            "message": str(last_error) if last_error else "All proxy attempts timed out.",
        }
        await Actor.push_data(failure_output)
        await Actor.fail(status_message=f"Extraction failed after {MAX_ATTEMPTS} attempts: {last_error}")


if __name__ == "__main__":
    asyncio.run(main())
