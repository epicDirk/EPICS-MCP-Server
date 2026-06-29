# Lokaler recsync-recceiver (Phase B / M2) auf den ESS-Prod-Bau gebracht (decision GR / Option C, P3 /
# Scope VOLL): empfängt die UDP-Announces, auf die der reccaster im e3-Test-IOC lauscht, und schreibt
# dessen Records automatisch nach ChannelFinder (essioc → reccaster → recceiver → CF).
#
# WORTGETREUES ESS-Rezept (gitlab.esss.lu.se/ics-docker/recceiver id 7168, branch main): recsync-Tag 1.8
# (immutabel) + die 4 ESS-Patches (patches/) + gepinnte requirements.txt + multi-stage venv. Die
# CF-Verbindung kommt seit P3/VOLL aus der docker.conf-ENV (NICHT mehr aus channelfinderapi.conf, entfernt).
# Zwei bewusste, kommentierte Abweichungen vom ESS-Verbatim:
#   B1 — der Artifactory-PyPI-Index ist Pflicht (channelfinder==3.0.0.post2 ist NICHT auf public PyPI).
#   B3 — recceiverId steht stabil literal in der docker.conf (unsere Container haben keinen stabilen
#        Hostname wie ESS-Prod-VMs; ESS lässt recceiverId auf socket.gethostname() fallen).
#
# Base = python:3.13-slim-BOOKWORM (Debian 12) — exakt wie ESS und NICHT der `slim`-Tag (B2: heute Alias
# auf slim-trixie/Debian 13). cfstore.py nutzt enum.StrEnum → braucht Python ≥3.11 (3.13 erfüllt es).
# Multi-Arch-Listen-Digest gepinnt (auffrischen: docker buildx imagetools inspect python:3.13-slim-bookworm).
FROM python:3.13-slim-bookworm@sha256:fcbd8dfc2605ba7c2eca646846c5e892b2931e41f6227985154a596f26ab8ed7 AS build

# Proxy für die ESS-INTERNEN Egress-Layer: artifactory.esss.lu.se ist nur über den HOST erreichbar (VPN/LAN),
# NICHT aus dem Docker-Container (Container-Egress NAT-tet nur ins öffentliche Internet — github.com geht,
# artifactory NICHT; live gemessen 2026-06-29). Darum braucht `pip -i artifactory` den Host-CONNECT-Proxy
# (sandbox/connect_proxy.py 8899, wie ioc-e3/channelfinder). Build mit NUR HTTPS_PROXY=http://host.docker.internal:8899
# (HTTP_PROXY LEER) — pip/git sind HTTPS → CONNECT-Tunnel; apt ist plain-HTTP gegen deb.debian.org und geht
# DIREKT, weil der apt-RUN die Proxy-Vars nicht exportiert (der CONNECT-only-Proxy könnte apts HTTP-GET nicht).
# Der Proxy-Wert erscheint im docker-history des BUILD-Stage (explizites ARG hebt Dockers Default-Scrubbing der
# predefined Proxy-Args auf), bleibt aber aus dem FINALEN Image: der Runtime-Stage ist ein separater FROM ohne
# Proxy-ARG/ENV (ARG wird nie ENV). Kein Secret (host:port ohne Credential).
ARG HTTPS_PROXY=""
ARG HTTP_PROXY=""
ARG RECCEIVER_VERSION=1.8

# git zum Klonen der recsync-Quelle (vanilla, Tag 1.8 = immutabel). apt als root, VOR USER recceiver.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash recceiver
USER recceiver
WORKDIR /home/recceiver

RUN export HTTPS_PROXY="$HTTPS_PROXY" HTTP_PROXY="$HTTP_PROXY" \
 && git clone --depth 1 --branch "$RECCEIVER_VERSION" https://github.com/ChannelFinder/recsync.git

# Die 4 ESS-Patches (vendored aus ics-docker/recceiver:main patches/) VOR dem Install applizieren.
# Reihenfolge wie ESS (expandvars vor cfstore — expandvars liefert die %(VAR)s-ENV-Interpolation, die
# cfstore + die ENV-docker.conf zur Laufzeit voraussetzen). Die 4 Patches treffen disjunkte Dateien
# (pyproject.toml / processors.py / cfstore.py), Apply-Erfolg ist reihenfolge-unabhängig.
WORKDIR /home/recceiver/recsync
COPY patches/expandvars.patch patches/cfstore.patch patches/channelowner.patch patches/pyproj.patch ./
RUN git apply expandvars.patch cfstore.patch channelowner.patch pyproj.patch

# Gepinnte Deps aus dem ESS-Artifactory-PyPI-Mirror (B1: channelfinder==3.0.0.post2 ist NICHT auf public
# PyPI — der Mirror ist anonym erreichbar). twisted/requests wären public byte-identisch, channelfinder NICHT.
WORKDIR /home/recceiver
COPY requirements.txt requirements.txt
RUN export HTTPS_PROXY="$HTTPS_PROXY" HTTP_PROXY="$HTTP_PROXY" \
 && python -m venv venv \
 && venv/bin/pip install --no-cache-dir \
      -i https://artifactory.esss.lu.se/artifactory/api/pypi/pypi-virtual/simple \
      -r requirements.txt

# recsync 1.8 server in dasselbe venv. Das patched pyproject pinnt channelfinder==3.0.0.post2 → schon
# erfüllt durch requirements.txt, kein Re-Resolve über die alte pyCFClient-zip-URL.
RUN export HTTPS_PROXY="$HTTPS_PROXY" HTTP_PROXY="$HTTP_PROXY" \
 && venv/bin/python -m pip install --no-cache-dir ./recsync/server

# Pin-Gate (QA-C8): die 3 ESS-Pins müssen EFFEKTIV installiert sein, sonst bricht der Build hart — statt
# still „self-built, aber nicht ESS-deckungsgleich". -i = case-insensitiv (pip freeze schreibt z. B. Twisted).
RUN venv/bin/pip freeze | grep -ixE 'channelfinder==3\.0\.0\.post2' \
 && venv/bin/pip freeze | grep -ixE 'twisted==22\.8\.0' \
 && venv/bin/pip freeze | grep -ixE 'requests==2\.28\.1'

# --- Runtime-Stage: IDENTISCHE Base + identischer venv-Pfad (Shebang-Invariante QA-C8) ----------------
FROM python:3.13-slim-bookworm@sha256:fcbd8dfc2605ba7c2eca646846c5e892b2931e41f6227985154a596f26ab8ed7

RUN useradd -ms /bin/bash recceiver
USER recceiver
WORKDIR /home/recceiver

# ESS-Default-ENV (aus ics-docker/recceiver Dockerfile): jede %(VAR)s der docker.conf bekommt hier einen
# Default → kein InterpolationMissingOptionError (B3). compose überschreibt die CHANNELFINDER_* + LOGLEVEL.
# CHANNELFINDER_PASSWORD=1234 ist der ESS-Image-Default-Test-Cred — per compose auf adminPass überschrieben.
ENV RECCEIVER_ADDRLIST=255.255.255.255:5049 \
    RECCEIVER_PROCS=cf \
    RECCEIVER_ANNOUNCE_INTERVAL=15.0 \
    RECCEIVER_TCP_TIMEOUT=15.0 \
    RECCEIVER_COMMIT_INTERVAL=5.0 \
    RECCEIVER_MAX_ACTIVE=20 \
    RECCEIVER_LOGLEVEL=WARN \
    CHANNELFINDER_URL=http://channelfinder \
    CHANNELFINDER_USERNAME=channelfinder \
    CHANNELFINDER_PASSWORD=1234 \
    CHANNELFINDER_INFOTAGS=""

COPY --from=build /home/recceiver/venv venv
COPY docker.conf docker.conf

# twistd startet den recceiver-Plugin aus dem venv (cwd = /home/recceiver). --pidfile= (kein pidfile),
# --nodaemon (Vordergrund, Container-PID-1-tauglich). Wie das ESS-Dockerfile.
CMD ["venv/bin/twistd", "--pidfile=", "--nodaemon", "recceiver", "--config", "docker.conf"]
