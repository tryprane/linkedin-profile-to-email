import os
import sys
import time
import http.server
import ssl
import threading
from scrapling.fetchers import StealthyFetcher

class TurnstileSolver:
    def __init__(self, port=8443):
        self.port = port
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.page_dir = os.path.join(self.base_dir, 'page')
        self.cert_file = os.path.join(self.page_dir, 'cert.crt')
        self.key_file = os.path.join(self.page_dir, 'cert.key')
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

    def solve(self, proxy_url=None, timeout=30):
        self.start_local_server()
        solved_token = None

        def on_page_ready(page):
            nonlocal solved_token
            try:
                # Wait for Turnstile to initialize and load
                page.wait_for_function("document.getElementById('wstat') && document.getElementById('wstat').textContent.includes('ready')", timeout=10000)
                
                # Wait for the token callback
                page.wait_for_function("""() => Boolean(
                    (document.getElementById('widget') && document.getElementById('widget').getAttribute('data-token')) ||
                    (document.querySelector('[name="cf-turnstile-response"]') && document.querySelector('[name="cf-turnstile-response"]').value) ||
                    window.__solved_token__ ||
                    window.turnstileToken
                )""", timeout=20000)

                solved_token = page.evaluate("""() => (
                    (document.getElementById('widget') && document.getElementById('widget').getAttribute('data-token')) ||
                    (document.querySelector('[name="cf-turnstile-response"]') && document.querySelector('[name="cf-turnstile-response"]').value) ||
                    window.__solved_token__ ||
                    window.turnstileToken
                )""")
            except Exception as e:
                print(f"[solver] Error during page action: {e}")

        try:
            print("[solver] Launching Scrapling StealthyFetcher with solve_cloudflare=True...")
            extra_flags = [
                f'--host-resolver-rules=MAP tools.mailmeteor.com 127.0.0.1:{self.port}, EXCLUDE challenges.cloudflare.com',
                f'--proxy-bypass-list=127.0.0.1;localhost;tools.mailmeteor.com;tools.mailmeteor.com:{self.port}',
                '--ignore-certificate-errors',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ]

            fetch_kwargs = {
                "headless": True,
                "solve_cloudflare": True,
                "extra_flags": tuple(extra_flags),
                "page_action": on_page_ready,
                "timeout": timeout * 1000
            }

            if proxy_url:
                bypass_list = f"127.0.0.1,localhost,tools.mailmeteor.com,tools.mailmeteor.com:{self.port}"
                if "@" in proxy_url:
                    auth_part, host_part = proxy_url.replace("http://", "").replace("https://", "").split("@")
                    user, pwd = auth_part.split(":")
                    server = f"http://{host_part}"
                    fetch_kwargs["proxy"] = {
                        "server": server,
                        "username": user,
                        "password": pwd,
                        "bypass": bypass_list
                    }
                else:
                    fetch_kwargs["proxy"] = {
                        "server": proxy_url,
                        "bypass": bypass_list
                    }

            StealthyFetcher.fetch(
                f'https://tools.mailmeteor.com:{self.port}',
                **fetch_kwargs
            )
        except Exception as err:
            print(f"[solver] Fetcher error: {err}")
        finally:
            self.stop_local_server()

        return solved_token
