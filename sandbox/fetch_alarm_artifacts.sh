#!/usr/bin/env bash
# fetch_alarm_artifacts.sh — lädt die zwei ESS-Alarm-Artefakte (Release 5.0.052) vom anonymen Artifactory
# in die Build-Kontexte sandbox/alarm-server/ bzw. sandbox/alarm-logger/ und verifiziert sie per sha256.
#
# Hintergrund (decision GR / Option C, P4): der HOST erreicht artifactory.esss.lu.se anon (kein Token, kein
# Proxy); der Docker-Build-Container NICHT (Container-Egress erreicht nur das öffentliche Internet, QA-P3).
# Darum: am Host ziehen → die Dockerfiles nehmen die Datei per COPY (NICHT ADD <artifactory-url>).
# Die Artefakte sind gitignored (sandbox/alarm-{server,logger}/*.{tar.gz,jar}, ~190 MB) — die Reproduzier-
# barkeit kommt aus DIESEM Skript + den sha256-Pins (auch im jeweiligen Dockerfile per `sha256sum -c` geprüft).
#
# Aufruf (am Host, git-bash): bash sandbox/fetch_alarm_artifacts.sh
set -euo pipefail

BASE="https://artifactory.esss.lu.se/artifactory/libs-release-local/org/phoebus"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SERVER_TGZ="service-alarm-server-5.0.052-bin.tar.gz"
SERVER_SHA="0323bc7858f6425ac340ca73d022561092b4b796c2ad623d6d303beed1f9bd0f"
LOGGER_JAR="service-alarm-logger-5.0.052.jar"
LOGGER_SHA="124c82f8d9b764e969c6e8d0f017f19a6e62f4631f6c0d6e5dc4691b0e149b2c"

mkdir -p "$HERE/alarm-server" "$HERE/alarm-logger"

echo "[fetch] alarm-server Tarball (~81 MB) → sandbox/alarm-server/"
curl -fL --retry 5 --retry-delay 3 -o "$HERE/alarm-server/$SERVER_TGZ" \
  "$BASE/service-alarm-server/5.0.052/$SERVER_TGZ"
echo "$SERVER_SHA  $HERE/alarm-server/$SERVER_TGZ" | sha256sum -c -

echo "[fetch] alarm-logger Fat-Jar (~106 MB) → sandbox/alarm-logger/"
curl -fL --retry 5 --retry-delay 3 -o "$HERE/alarm-logger/$LOGGER_JAR" \
  "$BASE/service-alarm-logger/5.0.052/$LOGGER_JAR"
echo "$LOGGER_SHA  $HERE/alarm-logger/$LOGGER_JAR" | sha256sum -c -

echo "[fetch] OK — beide Artefakte geladen + sha256 verifiziert."
