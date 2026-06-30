#!/usr/bin/env bash
# fetch_archiver_artifact.sh — lädt das ESS-EPICS-Archiver-Appliance-Release 2.1.1 vom anonymen
# Artifactory in den Build-Kontext sandbox/archiver/ und verifiziert es per sha256.
#
# Hintergrund (decision GR / Option C, P5): der HOST erreicht artifactory.esss.lu.se anon (kein Token,
# kein Proxy); der Docker-Build-Container NICHT (Container-Egress erreicht nur das öffentliche Internet,
# QA-P3). Darum: am Host ziehen → sandbox/archiver/Dockerfile nimmt die Datei per COPY (NICHT
# `ADD <artifactory-url>`). Das Artefakt ist gitignored (sandbox/archiver/*.tar.gz, 340 MB) — die
# Reproduzierbarkeit kommt aus DIESEM Skript + dem sha256-Pin (auch im Dockerfile per `sha256sum -c`).
#
# Connector/J 5.1.48 + Tomcat 9.0.85 werden NICHT hier gezogen: der Build-Container erreicht Maven
# Central direkt (Connector via ADD im Dockerfile), und Tomcat kommt aus dem offiziellen Base-Image.
#
# Aufruf (am Host, git-bash): bash sandbox/fetch_archiver_artifact.sh
set -euo pipefail

# Kanonische ESS-Rollen-URL (defaults/main.yml epicsarchiverap_url). Das gespiegelte -remote-cache
# liefert byte-identisch (gleiche sha256) — beide anon 200.
URL="https://artifactory.esss.lu.se/artifactory/epics-archiver-release-remote/2.1.1/archappl_v2.1.1.tar.gz"
SHA="8c19a1af45c28fbbcb177ce6e73744371657532da5a0fc8fdb4b2b1385e9d7c4"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HERE/archiver/archappl_v2.1.1.tar.gz"

mkdir -p "$HERE/archiver"

echo "[fetch] archappl_v2.1.1.tar.gz (~340 MB) → sandbox/archiver/"
curl -fL --retry 5 --retry-delay 3 -o "$DEST" "$URL"
echo "$SHA  $DEST" | sha256sum -c -

echo "[fetch] OK — Artefakt geladen + sha256 verifiziert."
