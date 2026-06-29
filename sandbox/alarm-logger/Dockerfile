# Lokaler Phoebus alarm-logger auf den ESS-Prod-Deploy-Stand 5.0.052 gebracht (decision GR / Option C, P4):
# vorher Upstream-`:master` (6.0.0-SNAPSHOT). ESS pinnt im Prod-Deploy (ics-ans-alarm-server) den Release
# 5.0.052; das Artefakt liegt anonym auf Artifactory (libs-release-local/org/phoebus/). SELF-BUILD, weil ESS
# kein Docker-Image bereitstellt und 5.0.052 keinen GHCR-Tag hat.
#
# Der Logger ist ein Spring-Boot Fat-Jar (self-contained) → direkt `java -jar`, kein lib/ daneben nötig.
# Beschaffung am HOST (sandbox/fetch_alarm_artifacts.sh) + COPY (ADD <artifactory-url> geht NICHT — Container-
# Egress erreicht artifactory nicht; QA-P3). command kommt aus dem compose (bare Jar via WORKDIR /opt).
#
# Der gefürchtete ES-8-Client-BLOCKER ist quellcode-tot (8-Agenten-QA + Live-Re-Stichprobe am Tag ESS-5.0.052,
# commit 718af74a): services/alarm-logger/.../ElasticClientHelper.java nutzt co.elastic.clients...
# ElasticsearchClient (neuer ES-8-Java-Client), elasticsearch-java:8.2.0; RestHighLevelClient = 0 Treffer in
# Quelle+POM → CSS-Issue #2273 N/A. ES 8.2.3 ist damit reine Pin-Treue (5.0.052 liefe auch gegen 8.18).
#
# Base = eclipse-temurin:17-jre (Java 17, identischer Index-Digest wie CF/alarm-server; Rolling Tag → DIESEN
# Digest pinnen). PIN-AFTER-VERIFY: Base-Digest + Artefakt-sha256 (RUN sha256sum -c gegen die geladenen Bytes).
FROM eclipse-temurin:17-jre@sha256:d226a3132511d057267330beeca73804275899aacdea331b7bd8313bb1506a7a
WORKDIR /opt
COPY service-alarm-logger-5.0.052.jar /opt/
RUN echo "124c82f8d9b764e969c6e8d0f017f19a6e62f4631f6c0d6e5dc4691b0e149b2c  service-alarm-logger-5.0.052.jar" | sha256sum -c -
# command aus dem compose (Shell-Wrapper /bin/bash -c bleibt — -D-Props mit Spaces): java -D... -jar service-alarm-logger-5.0.052.jar -noshell ...
