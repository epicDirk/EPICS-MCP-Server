# Minimaler read-only Mock der ESS Naming Service REST-API für die lokale Sandbox (Test-Double).
# stdlib-only (kein pip) -> COPY genügt; kein Multi-Stage, kein Proxy/Artifactory (anders als recceiver).
# Bewusst NICHT digest-gepinnt (Test-Double, keine ESS-Reproduzierbarkeits-Anforderung).
FROM python:3.13-slim
COPY server.py /app/server.py
# Container-intern 0.0.0.0 (Bridge-/Publish-erreichbar); die Host-Isolation macht der 127.0.0.1-Publish in compose.
CMD ["python", "/app/server.py"]
