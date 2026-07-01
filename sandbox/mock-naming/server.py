#!/usr/bin/env python3
"""Minimal read-only mock of the ESS Naming Service REST API for the local sandbox.

A TEST DOUBLE (not the real service). Serves exactly what epics_pv_mcp.services.naming_client needs
so diagnose_connection's cause tree (unregistered / name_typo / withheld-on-outage) becomes
live-testable. Localhost-only, no auth, no writes, no ESS egress.

Routes:
  GET  /rest/deviceNames/{name}  -> 200 {"name","status":"ACTIVE",...} if {name} is a seeded device;
                                    404 otherwise (= not registered -> name_typo). 404, NOT 5xx: the
                                    client retries 502/503/504 with backoff.
  GET  /                         -> 200  (the container healthcheck does a GET on /)
  HEAD /                         -> 200  (naming_client.check_connectivity() HEADs base_url)

Seed: MOCK_NAMING_ACTIVE (comma-separated device names; default the sandbox device). Bind 0.0.0.0
INSIDE the container so the published 127.0.0.1 host port reaches it — the host isolation is the
127.0.0.1-publish in docker-compose, NOT a container loopback bind (same IOC INTF trap lesson).
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_ACTIVE = {n for n in os.getenv("MOCK_NAMING_ACTIVE", "FBIS-DLN01:Ctrl-EVR-01").split(",") if n}
_PORT = int(os.getenv("MOCK_NAMING_PORT", "8099"))
_PREFIX = "/rest/deviceNames/"


def _device_element(name: str) -> dict[str, str]:
    """A minimal-but-shaped DeviceNameElement; the client reads only the status field."""
    return {"name": name, "status": "ACTIVE", "description": "sandbox mock device"}


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: object | None = None) -> None:
        body = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:  # check_connectivity() liveness probe
        self._send(200)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, {"service": "mock-ess-naming"})
        elif path.startswith(_PREFIX):
            name = path[len(_PREFIX):]  # keep the literal colons; never split on ':' or '/'
            if name and name in _ACTIVE:
                self._send(200, _device_element(name))
            else:
                self._send(404, {"message": "device name not registered"})
        else:
            self._send(404, {"message": "not found"})

    def log_message(self, *args: object) -> None:  # keep the container log quiet
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", _PORT), _Handler).serve_forever()
