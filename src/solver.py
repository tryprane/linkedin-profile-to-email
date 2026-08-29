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
            print("[solver] Launching stealth browser to solve Turnstile...")
            fetch_kwargs = {
                "google_search": False,
                "additional_args": {
                    'args': [
                        f'--host-resolver-rules=MAP tools.mailmeteor.com 127.0.0.1:{self.port}, EXCLUDE challenges.cloudflare.com',
                        f'--proxy-bypass-list=127.0.0.1;localhost;tools.mailmeteor.com;tools.mailmeteor.com:{self.port}',
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
                },
                "page_action": on_page_ready,
                "timeout": timeout * 1000
            }
            if proxy_url:
                fetch_kwargs["proxy"] = proxy_url

            StealthyFetcher.fetch(
                f'https://tools.mailmeteor.com:{self.port}',
                **fetch_kwargs
            )
        except Exception as err:
            print(f"[solver] Fetcher error: {err}")
        finally:
            self.stop_local_server()

        return solved_token
