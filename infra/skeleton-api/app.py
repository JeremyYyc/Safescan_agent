import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in {"/health", "/health/live", "/health/ready"}:
            body = json.dumps(
                {"status": "ok", "service": self.server.service_name}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        body = json.dumps(
            {
                "error": {
                    "code": "resource_not_found",
                    "message": "Resource not found",
                }
            }
        ).encode()
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    import os

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.service_name = os.getenv("SERVICE_NAME", "skeleton-api")
    server.serve_forever()
