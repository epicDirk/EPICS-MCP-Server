# Lokaler ChannelFinder 4.7.3-alpha (Phase B / P2): der ESS-Prod-Pin (ics-ans-role-channelfinder).
# SELF-BUILD, weil 4.7.3-alpha KEINEN GHCR-Tag hat. Spiegelt das ESS-Rezept ics-docker/channelfinder
# (GitLab id 7114) 1:1 — FROM openjdk:17 + ADD <github-release-jar> + java -jar — OHNE die ESS-CA
# (localhost-Sandbox, kein ESS-TLS nötig).
#
# Build (Egress github.com release-assets; via Host-CONNECT-Proxy falls geblockt — wie recceiver/ioc-e3):
#   docker compose -f sandbox/docker-compose.yml build channelfinder
#   mit Proxy:  ... build --build-arg HTTPS_PROXY=http://host.docker.internal:8899 \
#                          --build-arg HTTP_PROXY=http://host.docker.internal:8899 channelfinder
# Base: ESS nutzt `openjdk:17` — dieser Docker-Hub-Tag ist DEPRECATED + ENTFERNT (docker.io → "not found").
# Maintained-Äquivalent = eclipse-temurin:17-jre (offizieller OpenJDK-17-Nachfolger, Ubuntu-basiert → hat bash
# für den /dev/tcp-Healthcheck). Bewusste, dokumentierte Abweichung — gleicher OpenJDK-17-Runtime (decision GR).
# Base-Digest + jar-sha256 nach Live-Verify gepinnt (PIN-AFTER-VERIFY 2026-06-29; self-built → kein Registry-Image-Digest):
# CF meldete version 4.7.3-SNAPSHOT, elastic Connected zu ES 8.11.3, coverage_audit cf_and_display 572 == Baseline.
FROM eclipse-temurin:17-jre@sha256:d226a3132511d057267330beeca73804275899aacdea331b7bd8313bb1506a7a

# Proxy NUR für die Egress-Layer (BuildKit nutzt die predefinierten Proxy-ARGs auch für ADD <url>).
ARG HTTPS_PROXY=""
ARG HTTP_PROXY=""

RUN useradd -ms /bin/bash channelfinder

# Die 4.7.3-alpha.jar aus dem immutablen GitHub-Release (= version-pinned). Identisch zu ESS' ADD-Zeile.
ADD --chown=channelfinder:channelfinder https://github.com/ChannelFinder/ChannelFinderService/releases/download/ChannelFinder-4.7.3-alpha/ChannelFinder-4.7.3-alpha.jar /opt/channelfinder/channelfinder.jar

# Byte-Pin der jar (PIN-AFTER-VERIFY): bricht den Build hart, falls das Release-Asset je verändert wird.
RUN echo "0408df5cd59bec0559a42d8fcd218b34c54ff495f496dabbf8c5c4b643259d1c  /opt/channelfinder/channelfinder.jar" | sha256sum -c -

USER channelfinder

# CMD wie ESS (bare java -jar; die gebündelte application.properties bringt HTTP:8080, demo_auth,
# Context /ChannelFinder/resources und elasticsearch.host_urls=$ELASTICSEARCH_HOST_URLS mit).
CMD ["java", "-jar", "/opt/channelfinder/channelfinder.jar"]
