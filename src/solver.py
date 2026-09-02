import logging
import os
import http.server
import ssl
import threading

from scrapling.fetchers import StealthyFetcher

# Silence third-party internal fetcher and automation logs
for name in ("scrapling", "scrapling.fetchers", "camoufox", "playwright", "urllib3"):
    logging.getLogger(name).setLevel(logging.ERROR)


class QuietRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


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
        handler = lambda *args, **kwargs: QuietRequestHandler(
            *args, directory=self.page_dir, **kwargs
        )
        self.server = http.server.HTTPServer(('127.0.0.1', self.port), handler)
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
        self.server.socket = ssl_ctx.wrap_socket(self.server.socket, server_side=True)

        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.05},
        )
        self.server_thread.daemon = True
        self.server_thread.start()

    def stop_local_server(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.server_thread:
            self.server_thread.join(timeout=1)
            self.server_thread = None

    def solve(self, proxy_url=None, timeout=25):
        self.start_local_server()
        solved_token = None

        def on_page_ready(page):
            nonlocal solved_token
            try:
                page.wait_for_function("""() => Boolean(
                    (document.getElementById('widget') && document.getElementById('widget').getAttribute('data-token')) ||
                    (document.querySelector('[name="cf-turnstile-response"]') && document.querySelector('[name="cf-turnstile-response"]').value) ||
                    window.__solved_token__ ||
                    window.turnstileToken ||
                    window.lastSolvedToken
                )""", timeout=20000)

                solved_token = page.evaluate("""() => (
                    (document.getElementById('widget') && document.getElementById('widget').getAttribute('data-token')) ||
                    (document.querySelector('[name="cf-turnstile-response"]') && document.querySelector('[name="cf-turnstile-response"]').value) ||
                    window.__solved_token__ ||
                    window.turnstileToken ||
                    window.lastSolvedToken
                )""")
            except Exception as e:
                print(f"[solver] Error during page action: {e}")

        try:
            fetch_args = [
                f'--host-resolver-rules=MAP tools.mailmeteor.com 127.0.0.1:{self.port}, EXCLUDE challenges.cloudflare.com',
                f'--proxy-bypass-list=127.0.0.1;localhost;tools.mailmeteor.com;tools.mailmeteor.com:{self.port}',
                '--ignore-certificate-errors',
                '--no-sandbox',
                '--no-first-run',
                '--disable-default-apps',
                '--disable-sync',
                '--mute-audio',
            ]

            fetch_kwargs = {
                "google_search": False,
                "network_idle": False,
                "retries": 1,
                "wait": 0,
                "additional_args": {
                    "args": fetch_args,
                    "viewport": {"width": 800, "height": 600},
                    "screen": {"width": 800, "height": 600},
                },
                "page_action": on_page_ready,
                "timeout": timeout * 1000,
            }

            if proxy_url:
                fetch_kwargs["proxy"] = proxy_url

            StealthyFetcher.fetch(
                f'https://tools.mailmeteor.com:{self.port}',
                **fetch_kwargs,
            )
        except Exception as err:
            print(f"[solver] Fetcher error: {err}")
        finally:
            self.stop_local_server()

        return solved_token
