#!/bin/bash
# Docker-Entrypoint der ESS EPICS Archiver Appliance 2.1.1 — EINE parametrisierte Image-Quelle,
# 4 Instanzen (decision GR / Option C, P5). INSTANCE ∈ {mgmt,engine,etl,retrieval} wählt:
#   - welches exploded WAR deployt wird (sein Servlet-Context-Path /<INSTANCE> WEIST DIE ROLLE ZU —
#     DefaultConfigService.java leitet MGMT/ENGINE/ETL/RETRIEVAL aus dem Context-Path ab, NICHT aus
#     der Identity oder INSTANCE),
#   - den HTTP-Connector-Port (17665/17666/17667/17668) + Shutdown-Port (16001-16004),
#   - (nur mgmt) den jdbc/archappl-Pool + maxHttpHeaderSize.
# Spiegelt ics-ans-role-epicsarchiverap setenv.sh.j2 / server.xml.j2 / context.xml.j2 @ v2.1.0,
# de-Jinja'd für die Docker-4-Container-Topologie (ein gemeinsames CATALINA_HOME, ein CATALINA_BASE
# pro Instanz). ARCHAPPL_MYIDENTITY (gemeinsam, aus dem compose) bindet alle 4 an die eine Appliance.
set -euo pipefail

: "${INSTANCE:?INSTANCE muss mgmt|engine|etl|retrieval sein}"

case "$INSTANCE" in
  mgmt)      CONNECTOR_PORT=17665; SERVER_PORT=16001; MAXHDR=' maxHttpHeaderSize="100000"'; POOL=mgmt  ;;
  engine)    CONNECTOR_PORT=17666; SERVER_PORT=16002; MAXHDR='';                            POOL=empty ;;
  etl)       CONNECTOR_PORT=17667; SERVER_PORT=16003; MAXHDR='';                            POOL=empty ;;
  retrieval) CONNECTOR_PORT=17668; SERVER_PORT=16004; MAXHDR='';                            POOL=empty ;;
  *) echo "FEHLER: unbekanntes INSTANCE=$INSTANCE" >&2; exit 1 ;;
esac

export CATALINA_HOME=/usr/local/tomcat
export CATALINA_BASE="/var/lib/tomcats/$INSTANCE"
CONF="$CATALINA_BASE/conf"

# Per-Instanz-CATALINA_BASE anlegen (ESS-Layout: ein CATALINA_HOME, ein CATALINA_BASE je Instanz)
mkdir -p "$CONF/Catalina/localhost" "$CATALINA_BASE/webapps" \
         "$CATALINA_BASE/logs" "$CATALINA_BASE/temp" "$CATALINA_BASE/work"

# ESS-Rolle legt /var/log/tomcat an (tasks/tomcat_base.yml); site_policies.py loggt dorthin
# (logging.basicConfig → archappl-policy.log). Fehlt der Ordner, scheitert das Policy-Execute beim
# archivePV mit IOError (Jython meldet ein fehlendes Parent-Dir missverständlich als „Permission denied").
mkdir -p /var/log/tomcat && chmod 0777 /var/log/tomcat

# NUR das WAR dieser Instanz deployen → Context-Path /<INSTANCE> (= Rollen-Zuweisung)
cp -a "/opt/archappl-webapps/$INSTANCE" "$CATALINA_BASE/webapps/$INSTANCE"

# server.xml rendern (Connector- + Shutdown-Port; mgmt zusätzlich maxHttpHeaderSize)
sed -e "s/@SERVER_PORT@/$SERVER_PORT/" \
    -e "s/@CONNECTOR_PORT@/$CONNECTOR_PORT/" \
    -e "s|@MAXHDR@|$MAXHDR|" \
    /opt/archappl-conf/server.xml.tmpl > "$CONF/server.xml"

# context.xml: mgmt trägt den jdbc/archappl-Pool, die anderen einen leeren Context
cp "/opt/archappl-conf/context-$POOL.xml" "$CONF/context.xml"

# Restliche conf aus dem Stock-Tomcat (web.xml, catalina.properties, logging, users)
for f in web.xml catalina.properties logging.properties tomcat-users.xml; do
  cp "$CATALINA_HOME/conf/$f" "$CONF/$f"
done

# ARCHAPPL-Umgebung (de-Jinja'd setenv.sh.j2). ARCHAPPL_MYIDENTITY kommt aus dem compose (gemeinsam).
export ARCHAPPL_MYIDENTITY="${ARCHAPPL_MYIDENTITY:-appliance0}"
export ARCHAPPL_APPLIANCES=/opt/archappl-conf/appliances.xml
export ARCHAPPL_POLICIES=/opt/archappl-conf/site_policies.py
export ARCHAPPL_PROPERTIES_FILENAME=/opt/archappl-conf/archappl.properties
export ARCHAPPL_DEPLOY_DIR=/var/lib/tomcats
export TOMCAT_HOME="$CATALINA_HOME"
export ARCHAPPL_SHORT_TERM_FOLDER=/home/archappl/sts/ArchiverStore
export ARCHAPPL_MEDIUM_TERM_FOLDER=/home/archappl/mts/ArchiverStore
export ARCHAPPL_LONG_TERM_FOLDER=/home/archappl/lts/ArchiverStore
mkdir -p /home/archappl/sts/ArchiverStore /home/archappl/mts/ArchiverStore /home/archappl/lts/ArchiverStore

# engine nutzt pures CAJ (archappl.properties useCAJ=true) → native JCA-Libs nicht nötig, aber
# der ESS-LD_LIBRARY_PATH der engine-Webapp wird zur Treue dennoch gesetzt.
if [ "$INSTANCE" = "engine" ]; then
  export LD_LIBRARY_PATH="$CATALINA_BASE/webapps/engine/WEB-INF/lib/native/linux-x86_64:${LD_LIBRARY_PATH:-}"
fi

# JVM: ESS-CATALINA_OPTS (G1GC, 512M Heap, 256M Metaspace). Der JMX-/Prometheus-Exporter-Agent der
# ESS-Rolle ist bewusst weggelassen (reines Monitoring, kein Funktions-Impact auf is_archived/get_pv_history).
export CATALINA_OPTS="-XX:MaxMetaspaceSize=256M -XX:+UseG1GC -Xms512M -Xmx512M -ea"

exec "$CATALINA_HOME/bin/catalina.sh" run
