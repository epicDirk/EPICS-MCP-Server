# Lokaler Phoebus alarm-server auf den ESS-Prod-Deploy-Stand 5.0.052 gebracht (decision GR / Option C, P4):
# vorher lief der Stack auf Upstream-`:master` (6.0.0-SNAPSHOT) — das ist NICHT der ESS-Kanon. ESS pinnt im
# Prod-Deploy (ics-ans-alarm-server) den Release 5.0.052; die Artefakte liegen anonym auf Artifactory
# (libs-release-local/org/phoebus/). SELF-BUILD, weil ESS kein Docker-Image für den Alarm-Stack bereitstellt
# (Deploy = Ansible/systemd) und 5.0.052 keinen GHCR-Tag hat.
#
# Beschaffung: das ESS-Artefakt wird am HOST gezogen (sandbox/fetch_alarm_artifacts.sh) und hier per COPY
# in den Build genommen. `ADD <artifactory-url>` im Dockerfile geht NICHT — der Container-Egress erreicht
# artifactory.esss.lu.se nicht (nur der Host über VPN/LAN; live gemessen P3/QA-P3). Der Host erreicht
# Artifactory anon (kein Token, kein Proxy) → kein Build-Proxy nötig.
#
# Tarball-Layout = `service-alarm-server-5.0.052/` mit Thin-Jar (88 KB) + lib/ (47 Dep-Jars, relativer
# Class-Path) — KEIN Startskript. ⚠ Darum WORKDIR = Entpack-Verzeichnis: das Jar MUSS neben seinem lib/
# stehen, sonst löst der relative Class-Path nicht auf. CMD/command kommt aus dem compose (bare Jar via WORKDIR).
#
# Base = eclipse-temurin:17-jre (Java 17, Bytecode-Major 61 — exakt wie P2/CF; Java>17 NICHT nötig, beide
# Services kompilieren gegen 17). Identischer Multi-Arch-Index-Digest wie das channelfinder-Image (am
# Verify-Zeitpunkt erfasst; eclipse-temurin:17-jre ist ein Rolling Tag → DIESEN Digest pinnen, Tag nicht
# später neu auflösen). PIN-AFTER-VERIFY: self-built → kein Registry-Image-Digest; Base-Digest + die
# Artefakt-sha256 (RUN sha256sum -c gegen die geladenen Bytes) sind die Pins.
FROM eclipse-temurin:17-jre@sha256:d226a3132511d057267330beeca73804275899aacdea331b7bd8313bb1506a7a
WORKDIR /opt
COPY service-alarm-server-5.0.052-bin.tar.gz /opt/
RUN echo "0323bc7858f6425ac340ca73d022561092b4b796c2ad623d6d303beed1f9bd0f  service-alarm-server-5.0.052-bin.tar.gz" | sha256sum -c - \
 && tar -xzf service-alarm-server-5.0.052-bin.tar.gz \
 && rm service-alarm-server-5.0.052-bin.tar.gz
# ⚠ PFLICHT: Thin-Jar braucht sein lib/ daneben (relativer Class-Path) → CWD = Entpack-Verzeichnis.
WORKDIR /opt/service-alarm-server-5.0.052
# command aus dem compose: java -jar service-alarm-server-5.0.052.jar -config Accelerator -server alarm-kafka:9092 -noshell
