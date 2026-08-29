import os
import re
import time
import asyncio
import json
import ssl
import urllib.request
import urllib.error
from apify import Actor
from src.solver import TurnstileSolver

def validate_and_normalize_linkedin_url(url: str) -> tuple[bool, str, str]:
    """
    Validates and normalizes a LinkedIn profile URL.
    Returns: (is_valid, normalized_url, error_message)
    """
    if not url or not isinstance(url, str):
        return False, "", "The 'linkedin_url' input is required."
    
    clean_url = url.strip()
    
    # Prepend https:// if protocol is omitted
    if clean_url.startswith("www.linkedin.com") or clean_url.startswith("linkedin.com"):
        clean_url = "https://" + clean_url
    elif not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        if "/" not in clean_url and not clean_url.startswith("http"):
            # Handle bare username or vanity handle (e.g. 'satyanadella')
            clean_url = f"https://www.linkedin.com/in/{clean_url}"
        else:
            clean_url = "https://" + clean_url

    # Regex validation for LinkedIn profile URLs
    linkedin_pattern = re.compile(
        r"^https?://(www\.)?linkedin\.com/in/([a-zA-Z0-9_-]+(?:%[0-9a-fA-F]{2})*)/?(\?.*)?$",
        re.IGNORECASE
    )
    
    match = linkedin_pattern.match(clean_url)
    if not match:
        return False, clean_url, "Invalid LinkedIn profile URL format. Expected: https://www.linkedin.com/in/username"
    
    username = match.group(2)
    normalized = f"https://www.linkedin.com/in/{username}"
    return True, normalized, ""

async def main():
    async with Actor:
        actor_input = await Actor.get_input() or {}
        raw_url = actor_input.get("linkedin_url", "")

        # Input Validation
        is_valid, linkedin_url, err_msg = validate_and_normalize_linkedin_url(raw_url)
        if not is_valid:
            Actor.log.error(f"Input validation error: {err_msg} (Received: '{raw_url}')")
            await Actor.push_data({
                "raw_input": raw_url,
                "found": False,
                "error": "invalid_input",
                "message": err_msg
            })
            await Actor.fail(status_message=err_msg)
            return

        Actor.log.info(f"Starting Email Finder for validated LinkedIn profile: {linkedin_url}")

        # Configure Apify Residential Proxy for API querying
        proxy_url = os.environ.get("PROXY_URL")
        proxy_config_input = actor_input.get("proxyConfiguration")
        try:
            if proxy_config_input:
                proxy_configuration = await Actor.create_proxy_configuration(
                    actor_proxy_input=proxy_config_input
                )
            else:
                proxy_configuration = await Actor.create_proxy_configuration(
                    groups=["RESIDENTIAL"]
                )
            if proxy_configuration:
                proxy_url = await proxy_configuration.new_url()
                Actor.log.info("Using Apify Residential Proxy for API query.")
        except Exception as e:
            if not proxy_url:
                Actor.log.warning(f"Could not initialize Apify Proxy: {e}. Falling back to direct connection.")

        # Solve Turnstile token using Scrapling StealthyFetcher
        Actor.log.info("Solving Cloudflare Turnstile challenge via Scrapling...")
        solver = TurnstileSolver()
        token = await asyncio.to_thread(solver.solve, linkedin_url=linkedin_url, timeout=35)

        if not token:
            Actor.log.error("Failed to solve Cloudflare Turnstile token.")
            await Actor.push_data({
                "linkedin_url": linkedin_url,
                "found": False,
                "error": "turnstile_solve_failed",
                "message": "Could not acquire a valid Turnstile token."
            })
            await Actor.fail(status_message="Turnstile challenge solve failed.")
            return

        Actor.log.info(f"Turnstile token acquired successfully: {token[:25]}...")

        # Query Mailmeteor Live Email Finder API
        api_url = f"https://tools.mailmeteor.com/api/email-finder/linkedin?cf-turnstile-response={token}"
        payload = {
            "linkedin_url": linkedin_url,
            "cf-turnstile-response": token,
            "token": token
        }
        post_data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": "https://mailmeteor.com",
            "Referer": "https://mailmeteor.com/email-finder/linkedin"
        }

        req = urllib.request.Request(api_url, data=post_data, headers=headers)
        ssl_unverified = ssl._create_unverified_context()

        if proxy_url:
            proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
            opener = urllib.request.build_opener(proxy_handler, urllib.request.HTTPSHandler(context=ssl_unverified))
        else:
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_unverified))

        try:
            Actor.log.info("Sending request to Mailmeteor API...")
            with opener.open(req, timeout=25) as resp:
                resp_bytes = resp.read()
                result = json.loads(resp_bytes.decode("utf-8"))
                
                output = {
                    "linkedin_url": linkedin_url,
                    "found": result.get("found", False),
                    "success": result.get("success", False),
                    "email": result.get("email"),
                    "validation": result.get("validation"),
                    "job_title": result.get("job_title"),
                    "company": result.get("company"),
                    "full_name": result.get("full_name"),
                    "raw": result
                }
                
                Actor.log.info(f"API result received: Found={output['found']}, Email={output['email']}")
                await Actor.push_data(output)
                await Actor.set_value("OUTPUT", output)

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            Actor.log.error(f"Mailmeteor API returned HTTP {e.code}: {err_body}")
            try:
                err_json = json.loads(err_body)
            except Exception:
                err_json = {"raw": err_body}
            
            output = {
                "linkedin_url": linkedin_url,
                "found": False,
                "http_status": e.code,
                "error": err_json.get("code", "http_error"),
                "message": err_json.get("message", "API request failed.")
            }
            await Actor.push_data(output)
            await Actor.set_value("OUTPUT", output)
            if e.code == 429:
                await Actor.fail(status_message="Mailmeteor rate limit reached. Retry in a few minutes.")
            else:
                await Actor.fail(status_message=f"Mailmeteor API error {e.code}")

        except Exception as err:
            Actor.log.error(f"Request failed: {err}")
            output = {
                "linkedin_url": linkedin_url,
                "found": False,
                "error": "request_exception",
                "message": str(err)
            }
            await Actor.push_data(output)
            await Actor.set_value("OUTPUT", output)
            await Actor.fail(status_message=f"Request failed: {err}")

if __name__ == "__main__":
    asyncio.run(main())
