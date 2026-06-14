# -*- coding: utf-8 -*-
"""Local web server for the NSR-Aegis Panama Canal MVP site."""

from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from panama_ai_core import get_panama_engine


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8601


class PanamaSiteHandler(SimpleHTTPRequestHandler):
    """Serve static files and expose the Panama prediction API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/predict":
            self._handle_predict(parsed.query)
            return

        if parsed.path in {"/", ""}:
            self.path = "/site/index.html"
        elif parsed.path in {"/styles.css", "/app.js"}:
            self.path = "/site" + parsed.path

        super().do_GET()

    def _handle_predict(self, query: str) -> None:
        try:
            params = parse_qs(query)
            payload = {
                "month": int(float(self._first(params, "month", "8"))),
                "precipitation_mm": float(self._first(params, "precipitation_mm", "210")),
                "avg_temp_c": float(self._first(params, "avg_temp_c", "28.7")),
                "sst_anomaly_c": float(self._first(params, "sst_anomaly_c", "0.8")),
            }

            engine = get_panama_engine()
            result = engine.predict_panama_conditions(**payload)
            self._send_json(result)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    @staticmethod
    def _first(params: dict[str, list[str]], key: str, default: str) -> str:
        values = params.get(key)
        return values[0] if values else default

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer((host, port), PanamaSiteHandler)
    if sys.stdout:
        print(f"NSR-Aegis Panama MVP running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    selected_port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    run(port=selected_port)
