import asyncio
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from apify import Actor

from src.solver import TurnstileSolver

SERVICE_ENDPOINT = "https://tools.mailmeteor.com/api/email-finder/linkedin"


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
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://tools.mailmeteor.com",
        "Referer": "https://tools.mailmeteor.com/email-finder/linkedin",
    }
    return urllib.request.Request(api_url, data=post_data, headers=headers)


def query_email_api(
    linkedin_url: str,
    token: str,
    proxy_url: str | None,
    timeout: int = 20,
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
                    "raw_input": raw_url,
                    "found": False,
                    "error": "invalid_input",
                    "message": error_message,
                }
            )
            await Actor.fail(status_message=error_message)
            return

        Actor.log.info(f"Starting Email Finder for: {linkedin_url}")

        # Enforce Apify Residential Proxy
        proxy_url = os.environ.get("PROXY_URL")
        try:
            proxy_configuration = await Actor.create_proxy_configuration(
                groups=["RESIDENTIAL"]
            )
            if proxy_configuration:
                proxy_url = await proxy_configuration.new_url()
                Actor.log.info("Apify Residential Proxy initialized successfully.")
            elif not proxy_url:
                raise RuntimeError("Apify Proxy is mandatory for email extraction.")
        except Exception as error:
            if not proxy_url:
                Actor.log.error(f"Failed to initialize Apify Proxy: {error}")
                await Actor.fail(status_message="Apify Proxy configuration is required.")
                return

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
                    "error": "turnstile_solve_failed",
                    "message": "Could not acquire a valid security token.",
                }
            )
            await Actor.fail(status_message="Security challenge solve failed.")
            return

        Actor.log.info("Security challenge resolved successfully.")

        try:
            Actor.log.info("Executing email extraction request...")
            result, transfer_bytes, latency = await asyncio.to_thread(
                query_email_api,
                linkedin_url,
                token,
                proxy_url,
            )
            Actor.log.info(
                f"Lookup completed in {latency:.2f}s "
                f"({transfer_bytes} body bytes transferred)."
            )
            output = {
                "linkedin_url": linkedin_url,
                "found": result.get("found", False),
                "success": result.get("success", False),
                "email": result.get("email"),
                "validation": result.get("validation"),
                "job_title": result.get("job_title"),
                "company": result.get("company"),
                "full_name": result.get("full_name"),
                "api_proxy_used": bool(proxy_url),
                "api_transfer_bytes": transfer_bytes,
            }
            Actor.log.info(
                f"Result: Found={output['found']}, Email={output['email']}"
            )
            await Actor.push_data(output)
            await Actor.set_value("OUTPUT", output)

        except urllib.error.HTTPError as error:
            error_body = error.read().decode("utf-8") if error.fp else ""
            Actor.log.error(f"API request returned HTTP {error.code}: {error_body}")
            try:
                error_json = json.loads(error_body)
            except Exception:
                error_json = {"raw": error_body}

            output = {
                "linkedin_url": linkedin_url,
                "found": False,
                "http_status": error.code,
                "error": error_json.get("code", "http_error"),
                "message": error_json.get("message", "API request failed."),
            }
            await Actor.push_data(output)
            await Actor.set_value("OUTPUT", output)
            if error.code == 429:
                await Actor.fail(
                    status_message="Rate limit reached. Please retry in a few moments."
                )
            else:
                await Actor.fail(status_message=f"Lookup API error HTTP {error.code}")

        except Exception as error:
            Actor.log.error(f"Request failed: {error}")
            output = {
                "linkedin_url": linkedin_url,
                "found": False,
                "error": "request_exception",
                "message": str(error),
            }
            await Actor.push_data(output)
            await Actor.set_value("OUTPUT", output)
            await Actor.fail(status_message=f"Request failed: {error}")


if __name__ == "__main__":
    asyncio.run(main())
