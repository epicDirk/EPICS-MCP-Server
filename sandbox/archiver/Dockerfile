# ESS EPICS Archiver Appliance 2.1.1 — 4-Instanz-Tomcat aus EINER parametrisierten Image-Quelle
# (decision GR / Option C, P5). Treue Docker-Übersetzung von ics-ans-role-epicsarchiverap @ v2.1.0
# (ESS-Prod-Stand); löst den pklaus-2019-Single-JVM/Redis-Bau ab.
#
#   - WARs aus dem ESS-RELEASE-Artefakt archappl_v2.1.1.tar.gz (am HOST gezogen via
#     sandbox/fetch_archiver_artifact.sh → COPY; der Build-Container erreicht artifactory.esss.lu.se
#     NICHT, nur der Host über VPN — QA-P3-Egress-Lehre; darum COPY statt `ADD <artifactory-url>`).
#   - Tomcat 9.0.85 + JDK 21 über das OFFIZIELLE Base-Image tomcat:9.0.85-jre21-temurin-jammy
#     (Canon: Tomcat 9.0.85 + OpenJDK 21; Appliance 2.1.x VERLANGT Tomcat 9 — 2.2.0 verlangt Tomcat 10).
#     cgroup-v2-sicher boot-getestet (Provider cgroupv2, Memory Limit 512M, JDK 21, kein NPE).
#   - MySQL Connector/J 5.1.48 (Treiber com.mysql.jdbc.Driver — „fine with MariaDB", role vars/main.yml),
#     von Maven Central gezogen (public → build-erreichbar) in das gemeinsame Tomcat-lib/.
#
# Die 4 Instanzen (mgmt/engine/etl/retrieval) kommen aus DIESEM Image: entrypoint.sh wählt WAR + Ports
# + (mgmt) JDBC-Pool aus der INSTANCE-Env. Die Webapp-Rolle bestimmt der Servlet-Context-Path.
# PIN-AFTER-VERIFY: Base @sha256 + Artefakt-sha256 + Connector/J-sha256 (alle per `sha256sum -c` hart geprüft).

# ---- Stage 1: die 4 WARs aus dem ESS-Artefakt exploden (braucht das `jar`-Tool → JDK) ----
# Digest-gepinnt (PIN-AFTER-VERIFY); reine Build-Stage (deterministisches WAR-Explode, Output durch
# die Artefakt-sha256 fixiert) — der Pin ist Reproduzierbarkeits-Hygiene wie bei den anderen Dockerfiles.
FROM eclipse-temurin:21-jdk@sha256:762d16be48b976c97801d198e5085b1f6facb13718a1e8fb67cb25d0b25337e1 AS expand
WORKDIR /build
COPY archappl_v2.1.1.tar.gz .
RUN echo "8c19a1af45c28fbbcb177ce6e73744371657532da5a0fc8fdb4b2b1385e9d7c4  archappl_v2.1.1.tar.gz" | sha256sum -c - \
 && tar -xzf archappl_v2.1.1.tar.gz mgmt.war engine.war etl.war retrieval.war \
 && for w in mgmt engine etl retrieval; do \
        mkdir -p "/webapps/$w" && (cd "/webapps/$w" && jar xf "/build/$w.war"); \
    done

# ---- Stage 2: Laufzeit (offizielles Tomcat 9.0.85 + JRE 21 Temurin, cgroup-v2-sicher) ----
FROM tomcat:9.0.85-jre21-temurin-jammy@sha256:1dba5912da376611dc8c63cc35e504697e3e87945fad0fc4442bf4d24d131e10

# Proxy-Args durchreichen (leer = direkt; BuildKit nutzt die predefinierten Proxy-ARGs auch für ADD <url>).
ARG HTTPS_PROXY=""
ARG HTTP_PROXY=""

# MySQL Connector/J 5.1.48 ins gemeinsame Tomcat-lib/ (nur mgmt öffnet den jdbc/archappl-Pool, aber ein
# geteiltes lib/ spiegelt das ESS-tomcat_base-Layout; auf den anderen 3 harmlos).
ADD https://repo1.maven.org/maven2/mysql/mysql-connector-java/5.1.48/mysql-connector-java-5.1.48.jar \
    /usr/local/tomcat/lib/mysql-connector-java-5.1.48.jar
RUN echo "56e26caaa3821f5ae4af44f9c74f66cf8b84ea01516ad3803cbb0e9049b6eca8  /usr/local/tomcat/lib/mysql-connector-java-5.1.48.jar" | sha256sum -c -

# Die 4 exploded Webapps (entrypoint deployt pro Container GENAU EINE per INSTANCE)
COPY --from=expand /webapps/ /opt/archappl-webapps/

# De-Jinja'd ESS-Config (geteilt, von jeder Instanz über ARCHAPPL_*-Env gelesen)
COPY appliances.xml archappl.properties site_policies.py server.xml.tmpl \
     context-mgmt.xml context-empty.xml /opt/archappl-conf/

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 17665 mgmt · 17666 engine · 17667 etl · 17668 retrieval · 16670 Hazelcast-Cluster (nur mgmt bindet)
EXPOSE 17665 17666 17667 17668 16670
ENTRYPOINT ["/entrypoint.sh"]
