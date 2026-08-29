import os
import sys
import asyncio
import http.server
import ssl
import threading
from playwright.async_api import async_playwright

class TurnstileSolver:
    def __init__(self, port=8443):
        self.port = port
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.page_dir = os.path.join(self.base_dir, 'page')
        self.cert_file = os.path.join(self.page_dir, 'cert.crt')
        self.key_file = os.path.join(self.page_dir, 'cert.key')
        self.cache_dir = os.path.join(self.base_dir, '.chrome_cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.server = None
        self.server_thread = None

    def start_local_server(self):
        handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(*args, directory=self.page_dir, **kwargs)
        self.server = http.server.HTTPServer(('127.0.0.1', self.port), handler)
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
        self.server.socket = ssl_ctx.wrap_socket(self.server.socket, server_side=True)

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()
        print(f"[solver] Embedded HTTPS server started at https://127.0.0.1:{self.port}")

    def stop_local_server(self):
        if self.server:
            self.server.shutdown()
            print("[solver] Embedded HTTPS server stopped.")

    async def solve_async(self, proxy_url=None, timeout=30):
        self.start_local_server()
        solved_token = None

        try:
            print("[solver] Launching Playwright browser...")
            async with async_playwright() as p:
                launch_args = [
                    f'--host-resolver-rules=MAP tools.mailmeteor.com 127.0.0.1:{self.port}, EXCLUDE challenges.cloudflare.com',
                    f'--proxy-bypass-list=127.0.0.1;localhost;tools.mailmeteor.com;tools.mailmeteor.com:{self.port}',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-background-networking',
                    '--disable-component-update',
                    '--disable-sync',
                    '--disable-default-apps',
                    '--disable-features=OptimizationHints,SafeBrowsing',
                    '--safebrowsing-disable-auto-update',
                    '--disable-client-side-phishing-detection',
                    '--no-first-run',
                    '--no-default-browser-check',
                    f'--disk-cache-dir={self.cache_dir}',
                    '--disk-cache-size=104857600',
                    '--ignore-certificate-errors',
                    '--no-sandbox',
                ]

                launch_kwargs = {
                    "args": launch_args,
                    "headless": True,
                    "ignore_default_args": ["--enable-automation"]
                }

                if proxy_url:
                    # Parse proxy url if string format
                    bypass_list = f"127.0.0.1,localhost,tools.mailmeteor.com,tools.mailmeteor.com:{self.port}"
                    if "@" in proxy_url:
                        auth_part, host_part = proxy_url.replace("http://", "").replace("https://", "").split("@")
                        user, pwd = auth_part.split(":")
                        server = f"http://{host_part}"
                        launch_kwargs["proxy"] = {"server": server, "username": user, "password": pwd, "bypass": bypass_list}
                    else:
                        launch_kwargs["proxy"] = {"server": proxy_url, "bypass": bypass_list}

                browser = await p.chromium.launch(**launch_kwargs)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
                    ignore_https_errors=True
                )
                
                # Add stealth evasions
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = { runtime: {} };
                """)

                page = await context.new_page()
                await page.goto(f'https://tools.mailmeteor.com:{self.port}', wait_until='domcontentloaded', timeout=timeout*1000)

                # Wait for Turnstile to initialize
                await page.wait_for_function("document.getElementById('wstat') && document.getElementById('wstat').textContent.includes('ready')", timeout=10000)

                # Wait for token
                await page.wait_for_function("""() => Boolean(
                    (document.getElementById('widget') && document.getElementById('widget').getAttribute('data-token')) ||
                    (document.querySelector('[name="cf-turnstile-response"]') && document.querySelector('[name="cf-turnstile-response"]').value) ||
                    window.__solved_token__ ||
                    window.turnstileToken
                )""", timeout=20000)

                solved_token = await page.evaluate("""() => (
                    (document.getElementById('widget') && document.getElementById('widget').getAttribute('data-token')) ||
                    (document.querySelector('[name="cf-turnstile-response"]') && document.querySelector('[name="cf-turnstile-response"]').value) ||
                    window.__solved_token__ ||
                    window.turnstileToken
                )""")

                await browser.close()
        except Exception as e:
            print(f"[solver] Error solving Turnstile: {e}")
        finally:
            self.stop_local_server()

        return solved_token
