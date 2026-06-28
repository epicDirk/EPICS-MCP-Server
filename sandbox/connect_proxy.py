"""Minimaler HTTPS-CONNECT-Forward-Proxy (stdlib only) — nur für den e3-Image-Build.

Läuft auf dem Windows-Host (der ESS-Artifactory via VPN erreicht). Der Build-Container
setzt HTTPS_PROXY=http://host.docker.internal:<port> -> conda tunnelt seine HTTPS-Requests
(CONNECT) durch diesen Proxy zum Host, der sie an Artifactory weiterreicht. Read-only
Durchleitung, keine Speicherung, kein Logging von Inhalten. Nach dem Build beenden.

Start:  python connect_proxy.py 8899
"""

import contextlib
import select
import socket
import sys
import threading

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8899


def _pipe(a: socket.socket, b: socket.socket) -> None:
    """Bidirektionale Byte-Durchleitung zwischen zwei Sockets bis einer schließt."""
    sockets = [a, b]
    try:
        while True:
            readable, _, _ = select.select(sockets, [], [], 120)
            if not readable:
                break
            for s in readable:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    except OSError:
        pass
    finally:
        for s in sockets:
            with contextlib.suppress(OSError):
                s.close()


def _handle(client: socket.socket) -> None:
    """Erwarte 'CONNECT host:port HTTP/1.1', öffne Upstream, splice durch."""
    req = b""
    while b"\r\n\r\n" not in req:
        chunk = client.recv(4096)
        if not chunk:
            client.close()
            return
        req += chunk
        if len(req) > 65536:
            client.close()
            return
    line = req.split(b"\r\n", 1)[0].decode("latin1")
    parts = line.split(" ")
    if len(parts) < 2 or parts[0].upper() != "CONNECT":
        client.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
        client.close()
        return
    host, _, port = parts[1].rpartition(":")
    try:
        upstream = socket.create_connection((host, int(port or 443)), timeout=25)
    except OSError:
        client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        client.close()
        return
    client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()


def main() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(128)
    print(f"CONNECT proxy listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)  # noqa: T201
    while True:
        client, _ = srv.accept()
        threading.Thread(target=_handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
