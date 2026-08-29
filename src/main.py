import os
import time
import asyncio
import json
from apify import Actor
from curl_cffi import requests
from src.solver import TurnstileSolver

async def main():
    async with Actor:
        actor_input = await Actor.get_input() or {}
        linkedin_url = actor_input.get("linkedin_url", "").strip()

        if not linkedin_url:
            Actor.log.error("Missing 'linkedin_url' in actor input.")
            await Actor.fail(status_message="Missing required field 'linkedin_url'.")
            return

        Actor.log.info(f"Starting Email Finder for: {linkedin_url}")

        # Configure Apify Residential Proxy with Sticky Session ID (to match Turnstile solver IP with API IP)
        proxy_url = os.environ.get("PROXY_URL")
        proxy_config_input = actor_input.get("proxyConfiguration")
        session_id = f"lead{int(time.time()*1000)}"
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
                proxy_url = await proxy_configuration.new_url(session_id=session_id)
                Actor.log.info(f"Using Apify Residential Proxy with sticky session: {session_id}")
        except Exception as e:
            if not proxy_url:
                Actor.log.warning(f"Could not initialize Apify Proxy: {e}. Falling back to direct connection.")

        # Check public IP via proxy
        if proxy_url:
            try:
                proxies = {"http": proxy_url, "https": proxy_url}
                ip_check = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=10, impersonate="chrome124")
                Actor.log.info(f"Exit IP via Apify Proxy: {ip_check.json().get('ip')}")
            except Exception as e:
                Actor.log.warning(f"IP check error: {e}")

        # Solve Turnstile token with matching proxy IP using Scrapling
        Actor.log.info("Solving Cloudflare Turnstile challenge via Scrapling...")
        solver = TurnstileSolver()
        token = await asyncio.to_thread(solver.solve, proxy_url=proxy_url, timeout=30)

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

        # Query Mailmeteor Live Email Finder API with Chrome TLS impersonation
        api_url = f"https://tools.mailmeteor.com/api/email-finder/linkedin?cf-turnstile-response={token}"
        payload = {
            "linkedin_url": linkedin_url,
            "cf-turnstile-response": token,
            "token": token
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Origin": "https://mailmeteor.com",
            "Referer": "https://mailmeteor.com/email-finder/linkedin",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site"
        }

        try:
            Actor.log.info("Sending request to Mailmeteor API via curl_cffi Chrome TLS...")
            proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
            
            response = requests.post(
                api_url,
                json=payload,
                headers=headers,
                proxies=proxies,
                timeout=25,
                impersonate="chrome124"
            )
            
            if response.status_code == 200:
                result = response.json()
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
            else:
                Actor.log.error(f"Mailmeteor API returned HTTP {response.status_code}: {response.text}")
                try:
                    err_json = response.json()
                except Exception:
                    err_json = {"raw": response.text}
                
                output = {
                    "linkedin_url": linkedin_url,
                    "found": False,
                    "http_status": response.status_code,
                    "error": err_json.get("code", "http_error"),
                    "message": err_json.get("message", "API request failed.")
                }
                await Actor.push_data(output)
                await Actor.set_value("OUTPUT", output)
                if response.status_code == 429:
                    await Actor.fail(status_message="Mailmeteor rate limit reached. Retry in a few minutes.")
                else:
                    await Actor.fail(status_message=f"Mailmeteor API error {response.status_code}")

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
