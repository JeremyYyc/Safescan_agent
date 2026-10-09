import unittest
from unittest.mock import patch

import httpx

from collect import Fetcher, allowed, extract


class ExtractionTests(unittest.TestCase):
    def test_hierarchy_lists_links_and_noise(self):
        html = b'''<html><head><meta property="article:published_time" content="2024-01-01"></head>
        <body><nav>GLOBAL NAV</nav><main><h1>Home</h1><h2>Alarms</h2><h3>Checks</h3>
        <ul><li><p>Inspect <a href="/manual">manual</a></p></li><li>Record results</li></ul>
        <div class="nsw-socials"><li>Facebook</li></div>
        <h2>Related information</h2><p>Unrelated link</p></main></body></html>'''
        data = extract(html, "https://www.nsw.gov.au/home")
        self.assertEqual(data["sections"][0]["heading_path"], ["Home", "Alarms", "Checks"])
        self.assertEqual(len(data["sections"][0]["blocks"]), 2)
        self.assertEqual(data["sections"][0]["blocks"][0]["links"][0]["url"], "https://www.nsw.gov.au/manual")
        self.assertNotIn("Facebook", data["content_text"])
        self.assertNotIn("GLOBAL NAV", data["content_text"])
        self.assertNotIn("Unrelated link", data["content_text"])
        self.assertEqual(data["published_at"], "2024-01-01")
        self.assertIsNone(data["source_updated_at"])

    def test_short_missing_main_requires_review(self):
        data = extract(b"<body><p>Small</p></body>", "https://www.nsw.gov.au/")
        self.assertIn("short_content", data["extraction_warnings"])
        self.assertIn("main_container_missing", data["extraction_warnings"])
        self.assertIn("missing_title", data["extraction_warnings"])


class NetworkTests(unittest.TestCase):
    def client(self, handler):
        fetcher = Fetcher()
        fetcher.client.close()
        fetcher.client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(fetcher.close)
        return fetcher

    def test_allowlist(self):
        for url in ("http://www.nsw.gov.au/", "https://www.nsw.gov.au.evil.test/", "https://user@www.nsw.gov.au/", "https://www.nsw.gov.au:444/"):
            self.assertFalse(allowed(url))

    @patch("collect.time.sleep")
    def test_redirect_checked_before_request(self, _):
        visited = []
        def handler(request):
            visited.append(str(request.url))
            return httpx.Response(302, headers={"location": "/admin"})
        fetcher = self.client(handler)
        with self.assertRaisesRegex(ValueError, "robots_disallowed"):
            fetcher.get("https://www.nsw.gov.au/start", permit=lambda u: not u.endswith("/admin"))
        self.assertEqual(len(visited), 1)

    @patch("collect.time.sleep")
    def test_rate_limit_stops_host(self, _):
        fetcher = self.client(lambda r: httpx.Response(429, headers={"Retry-After": "120"}))
        with self.assertRaisesRegex(ValueError, "rate_limited"):
            fetcher.get("https://www.nsw.gov.au/a")
        with self.assertRaisesRegex(ValueError, "host_stopped"):
            fetcher.get("https://www.nsw.gov.au/b")
        self.assertEqual(fetcher.attempts, 1)

    @patch("collect.time.sleep")
    def test_transport_retries_bounded(self, _):
        def handler(request):
            raise httpx.ReadTimeout("test timeout", request=request)
        fetcher = self.client(handler)
        with self.assertRaises(httpx.ReadTimeout):
            fetcher.get("https://www.nsw.gov.au/a")
        self.assertEqual(fetcher.attempts, 3)

    @patch("collect.time.sleep")
    def test_non_html_identifiable(self, _):
        fetcher = self.client(lambda r: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF"))
        self.assertEqual(fetcher.get("https://www.nsw.gov.au/a")[2]["content-type"], "application/pdf")

    @patch("collect.time.sleep")
    def test_response_budget(self, _):
        fetcher = self.client(lambda r: httpx.Response(200, content=b"a" * 20))
        with patch("collect.MAX_BYTES", 10), self.assertRaisesRegex(ValueError, "budget"):
            fetcher.get("https://www.nsw.gov.au/a")

    def test_run_attempt_budget(self):
        fetcher = self.client(lambda r: self.fail("must not send request"))
        fetcher.attempts = 30
        with self.assertRaisesRegex(ValueError, "budget"):
            fetcher.get("https://www.nsw.gov.au/a")


if __name__ == "__main__":
    unittest.main()
