# Lokaler recsync-recceiver (Phase B / M2): empfängt die UDP-Announces, auf die der reccaster im
# e3-Test-IOC lauscht, und schreibt dessen Records automatisch nach ChannelFinder
# (essioc → reccaster → recceiver → CF). VANILLA recsync 1.8 (immutabler Tag), KEINE ESS-Patches —
# die CF-Verbindung läuft über die mitgelieferte channelfinderapi.conf (pyCFClient-nativ).
#
# Build (Egress github.com + pypi.org; via Host-CONNECT-Proxy falls geblockt — wie ioc-e3):
#   docker compose -f sandbox/docker-compose.yml build recceiver
#   mit Proxy:  ... build --build-arg HTTPS_PROXY=http://host.docker.internal:8899 \
#                          --build-arg HTTP_PROXY=http://host.docker.internal:8899 recceiver
# Base = python:3.13-slim (NICHT das Upstream-python:3.11): cfstore.py nutzt enum.StrEnum → braucht
# Python ≥3.11 (das pyproject-requires-python>=3.6 ist dort inkonsistent); 3.13 erfüllt es. Multi-Arch-
# Listen-Digest gepinnt (auffrischen: docker buildx imagetools inspect python:3.13-slim).
FROM python:3.13-slim@sha256:2b7445fb71ca9cb15e9aab053fe8cb3162796f8e1d92ada12a49c766a811bc1e

# Proxy NUR für die Egress-Layer (Build-ARG; landet nicht im finalen Image-Env).
ARG HTTPS_PROXY=""
ARG HTTP_PROXY=""

# git zum Klonen der recsync-Quelle (vanilla, Tag 1.8 = immutabel).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /home/recceiver

# recsync 1.8 server installieren. pip zieht dabei pyCFClient v3.0.0 (im pyproject gepinnter GitHub-Zip)
# + twisted/requests/zope.interface (PyPI-Wheels). Versions-stabil, aber nicht byte-reproduzierbar
# (transitive Deps löst pip zur Build-Zeit; gleiche Ehrlichkeit wie der ioc-e3-conda-Build).
RUN export HTTPS_PROXY="$HTTPS_PROXY" HTTP_PROXY="$HTTP_PROXY" \
 && git clone --depth 1 --branch 1.8 https://github.com/ChannelFinder/recsync.git \
 && pip install --no-cache-dir ./recsync/server

# CF-Verbindung: pyCFClient (channelfinder._conf) liest [DEFAULT] aus /etc/channelfinderapi.conf,
# ~/.channelfinderapi.conf ODER ./channelfinderapi.conf (cwd). Beide robusten Orte belegen (cwd = WORKDIR
# + /etc) — identischer Inhalt; configparser nimmt bei Mehrfachfund den cwd-Eintrag. + recceiver-Config.
COPY channelfinderapi.conf /etc/channelfinderapi.conf
COPY channelfinderapi.conf docker.conf ./

# twistd startet den recceiver-Plugin im WORKDIR (cwd = /home/recceiver → channelfinderapi.conf wird gefunden).
# --pidfile= (leer = kein pidfile), --nodaemon (Vordergrund, Container-PID-1-tauglich). Wie der recsync-Upstream-Dockerfile.
CMD ["twistd", "--pidfile=", "--nodaemon", "recceiver", "--config", "docker.conf"]
