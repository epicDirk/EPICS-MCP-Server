# Lokale EPICS-Service-Sandbox

Lokale Services in Docker, gelesen vom **read-only** `epics-pv`-MCP gegen echte Services — **ohne**
ESS-Produktion (VPN-gated). ✅ **Inbound-Isolation (decision GW, 2026-06-30):** die Docker-Ports binden
**`127.0.0.1`** (nur Windows-Loopback) → die Sandbox ist **NICHT mehr vom ESS-LAN erreichbar**. Die alte
„0.0.0.0 ist WSL2-NAT-Pflicht"-Behauptung ist **empirisch widerlegt** (der native Windows-MCP erreicht
die `127.0.0.1`-Ports voll, auch PVA :5075). Damit ist auch die frühere Schreib-Exposition entschärft:
die 2 ASG-DEFAULT-Records `Temp1ThrUpCrt-SP`/`CmdRst` sind jetzt **nur noch über den Windows-Host**
erreichbar (vorher von jedem LAN-Host; `field(ASG,"private")` schützt die 7 Readbacks weiterhin am IOC).
✅ **Kein Service kündigt sich im ESS-Netz an (decision GW abgeschlossen):** Announcement-Audit aller
Services = kein ESS-Announce (Archiver-Hazelcast TCP/IP-per-Hostname/kein Multicast, ES `single-node`,
Kafka advertised bridge-intern, recsync Limited-Broadcast → lokale CF, kein mDNS); **IOC-Server-Beacons
explizit auf `127.0.0.1` gescoped** (`EPICS_CAS/PVAS…BEACON_ADDR_LIST`, AUTO=NO) → der IOC kann seine
PV-Identität nie auf ein routbares/ESS-Segment ankündigen. Ein **harter** generischer Egress-Block ist
auf Win10/WSL2 nur als `DOCKER-USER`-DROP-in-VM möglich (Hyper-V-Firewall/`.wslconfig`/Defender-Outbound
sind Win11-only bzw. wirkungslos; `internal:true` kappt das Publishing) — **recherchiert, aber bewusst
nicht gebaut** (bräuchte einen privileged `restart:always`-Sidecar; für eine no-emit-auditierte Test-Sandbox
überdimensioniert). Details: `ISOLATION-PLAN.md` §Anwendungs-Ergebnis. Zur **Laufzeit kein aktiver
ESS-Kontakt** (nur der einmalige Image-Build zieht e3-Pakete, s. u.).

## Komponenten

| Service | Was | Ports (host) |
|---|---|---|
| **`test-ioc`** | echtes **e3-IOC** (`require essioc`), Gerät `FBIS-DLN01:Ctrl-EVR-01`, serviert die `.db` über CA+PVA (QSRV2) | 5064/5065 (CA), 5075 (PVA) |
| **`elasticsearch`** (**Phase B / M1 — da**) | Backend für ChannelFinder (`:8.18.0`, single-node, xpack-security off) | 9200 |
| **`channelfinder`** (**Phase B / M1 — da**) | PV-Verzeichnis (REST), `ghcr.io/channelfinder/channelfinderservice:ChannelFinder-5.1.0`; API nativ unter `/ChannelFinder/resources/…` | 8080 |
| **`recceiver`** (**Phase B / M2 — LIVE, ESS-Bau VOLL**) | recsync 1.8 + die 4 ESS-Patches (`pyproj`/`cfstore`/`expandvars`/`channelowner`) + gepinnte requirements + multi-stage venv (wortgetreu `ics-docker/recceiver`, decision GR/P3); empfängt die reccaster-Records des `test-ioc` → schreibt sie auto nach CF | — (container-intern, UDP 5049) |
| **`archiver-mariadb`** (**Phase C / C-1 — ESS 2.1.1**) | Config-/PVTypeInfo-DB (`mariadb:10.11`, db/user/pw `archappl`, charset utf8mb3); DDL via `/docker-entrypoint-initdb.d/` | — (container-intern, 3306) |
| **`archiver-mgmt`** (**Phase C / C-1 — ESS 2.1.1**) | Appliance **mgmt**-Webapp (Hazelcast-Cluster-**Server**, bootet zuletzt) → `is_archived` + Seed `archivePV` | 17665 |
| **`archiver-engine` / `-etl` / `-retrieval`** (**Phase C / C-1**) | Appliance **engine** (schreibt STS, CA→`test-ioc`) / **etl** (STS→MTS→LTS) / **retrieval** (`get_pv_history`) — Hazelcast-Clients | retrieval **17668** (host); engine/etl container-intern |
| **`mock-naming`** (**Tier 3 — opt-in, Profil `naming`**) | winziges **read-only Test-Double** der ESS-Naming-REST (`stdlib http.server`); aktiviert den vollen `diagnose_connection`-Cause-Baum (`unregistered`/`name_typo`/`withheld-on-outage`) live. Kein ESS-Egress, kein Auth, kein Write | 8099 |

### ChannelFinder hochfahren (M1 — Seed-first)

```powershell
docker ps                                                                       # frisch prüfen (Multi-Window!)
docker compose -f sandbox/docker-compose.yml up -d elasticsearch channelfinder  # ES + CF (eigenes Netz; test-ioc unberührt)
curl -fs "http://localhost:8080/ChannelFinder/resources/channels?~name=*"        # erwartet: []  (CF up, API nativ /ChannelFinder)
EPICS-MCP-Server\.venv\Scripts\python.exe sandbox/seed/seed_channelfinder.py     # Fallback-Seed (M2 auto-populiert jetzt live; Seed = Fallback)
```

**Auth (am CF-5.1.0-Image aktiv = `demo_auth`, NIE Produktion):** `admin/adminPass` (Schreiben/Seed); Lesen
braucht keine Auth. Die cf.ldif-Creds `admin/1234` gehören zur *deaktivierten* embedded-LDAP-Variante (ESS-Prod).
**Context-Path:** CF 5.1.0 mappt nativ unter `/ChannelFinder` → **kein** `SERVER_SERVLET_CONTEXT_PATH`-Env setzen
(verdoppelt sonst zu `/ChannelFinder/ChannelFinder`). MCP-Aktivierung: `EPICS_MCP_CHANNELFINDER_URL=http://localhost:8080/ChannelFinder`
(s. Tabelle unten; wirkt erst im neuen Fenster).

### M2 — echtes Auto-Populate (reccaster → recceiver → ChannelFinder)

Statt zu seeden schreibt der **recceiver** die Records des IOC automatisch nach CF: der `essioc`-**reccaster**
im `test-ioc` lauscht auf `0.0.0.0:5049`; der **recceiver** (`sandbox/recceiver/`, **ESS-Bau VOLL: recsync 1.8 +
die 4 ESS-Patches**, decision GR/P3) sendet alle 15 s einen UDP-Broadcast (`255.255.255.255:5049`, subnetz-
unabhängig); der reccaster verbindet sich per UDP-Quell-IP zurück und überträgt seine Records. **CF-Verbindung
seit P3 über die `docker.conf`-ENV** (`cfstore.patch`+`expandvars.patch`: `cfstore` ruft jetzt
`ChannelFinderClient(BaseURL=%(CHANNELFINDER_URL)s, …, verify_ssl=False)`; `channelfinderapi.conf` ist **entfernt**) —
die `CHANNELFINDER_URL`/`USERNAME`/`PASSWORD` setzt der compose-`environment:`-Block des recceiver-Service
(`http://channelfinder:8080/ChannelFinder`, `admin/adminPass`). `docker.conf` `[cf]` trägt zudem
`alias/recordType/recordDesc` + `cleanOnStart` + den festen `recceiverId=recsync-sandbox` (literal, **B3** — bewusste
Abweichung vom ESS-Verbatim, da Docker-Container keinen stabilen Hostname haben; so inaktiviert das Clean NUR die
recceiver-eigenen Kanäle; die admin-geseedeten M1-Kanäle bleiben unberührt).

**recceiver bauen + starten (gegated — Container-Lifecycle, vorher `docker ps`):**

```powershell
# ⚠ artifactory.esss.lu.se ist ESS-INTERN → der Build-Container erreicht es NICHT direkt (github.com schon).
# Pflicht (P3, channelfinder==3.0.0.post2 ist nur auf Artifactory): Host-CONNECT-Proxy mit ECHTER CPython starten
# — NICHT dem Store-Shim WindowsApps\python.exe (dessen AppContainer blockt non-loopback → Container bekommt errno 111):
#   & "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe" sandbox/connect_proxy.py 8899   # Hintergrund
# Build mit NUR HTTPS_PROXY (HTTP_PROXY leer lassen → apt geht direkt am CONNECT-only-Proxy vorbei):
$env:HTTPS_PROXY="http://host.docker.internal:8899"; docker compose -f sandbox/docker-compose.yml build recceiver
# Proxy nach dem Build SOFORT stoppen (garantiert, auch bei Build-Fehler) + $env:HTTPS_PROXY wieder leeren.
# Minimaler Blast-Radius (CF/ES laufen lassen): nur test-ioc dem Netz beitreten + recceiver gegen das laufende CF:
docker compose -f sandbox/docker-compose.yml up -d --no-deps --force-recreate test-ioc   # ⚠ PVA-5075-Smoke davor/danach!
docker compose -f sandbox/docker-compose.yml up -d --no-deps recceiver
```

> ⚠️ Der `test-ioc`-Recreate (Netz-Join) trägt **PVA-5075** (alle 12 epics-pv-Tools) → davor/danach
> `get_pv_value("FBIS-DLN01:Ctrl-EVR-01:12VValue")` smoke-testen; bei kaputtem PVA `test-ioc` ohne `networks:`
> zurückrollen (Port-Publishing 5075 überlebt den Netz-Wechsel — verifiziert). Ein **voller** `compose up`
> würde zusätzlich cf-channelfinder (Healthcheck) + ggf. elasticsearch (@sha256-Pin) recreaten — der
> `--no-deps`-Weg vermeidet das.

**Verifikation (live bestätigt 2026-06-28):** recceiver-Log zeigt `CF_COMMIT` + `Total channels to update: 130`;
reccaster `RecSync-State-Sts` läuft bis **`Done`**; ein **NIE geseedetes** Record (`3V3Value`) liegt mit
`iocName=FBIS-DLN01-Ctrl-EVR-01`/`hostName=epics-sandbox-test-ioc`/`pvStatus=Active` in CF (kein Seed-Lauf). Test:
`EPICS_SANDBOX_RECSYNC=1` (+ `EPICS_SANDBOX=1 EPICS_SANDBOX_CF=1` + PVA-Env) → `test_find_channels_no_seed`.
**Seed (`seed_channelfinder.py`) bleibt als Fallback**, falls die Netzwerk-Kette mal nicht steht.

## Das e3-Test-IOC (`ioc-e3/`)

**Echtes e3, nicht „softIocPVX + lose .db":** `st.cmd` macht `require essioc` + `iocshLoad
common_config.iocsh` → lädt autosave/caputlog/iocStats/recsync/access-security; `dbLoadRecords` lädt
`fbis-dln01-evr.db` (9 Records: 2 mbbi/1 bi/3 ai/1 ao/1 calc/1 bo mit EGU/Limits/Alarm/DESC, ESS-Namens-
konvention `Sec-Sub:Dis-Dev-Idx:Signal`; Signal-Namen aus dem BIS-Dataset EVR-AMC slot2). **`iocsh` wrappt
`softIocPVX`** → CA + PVA (QSRV2).

> **Ehrliche Einordnung:** Dies ist ein **lokales Test-/Sim-IOC**, KEIN Komitee-Artefakt und KEIN echtes
> mrfioc2-EVR-IOC — in Produktion liefert das mrfioc2-Modul die EVR-PVs; hier sind es Soft-Records mit
> ESS-konformen Namen/Feldern, damit der MCP gegen realistische ESS-PVs testet.

### W2 — voller EVR-Spiegel (`fbis-dln01-evr-full.db`)

Über die 9 kuratierten Records hinaus bedient das IOC den **vollen** EVR-Registersatz, den die fbis-Displays
referenzieren — **567 Sim-Records** — **bis auf eine bewusst injizierte Lücke** (`DlyGen0Prescaler-SP`). Damit
kollabiert `cf_unregistered` (Phase A) gegen das volle fbis auf **genau diese eine Lücke** statt auf das
645/650-Rauschen des 9-Record-Spielzeugs („gesunder Spiegel + saubere Lücke"-Beweis; W2-Live-Test
`test_cf_unregistered_w2_full_mirror_collapses_to_gap`).

- **Quelle = `ioc-e3/evr-records.txt`** (573 distinct Record-Namen), geerntet aus `crossplane_check.pvs_linked`
  auf `BIS/fbis-systemexpert` bei **DEFAULT `context_cap=256`** (prefix-gestrippt + `_record_name`-normalisiert).
  Die Namen stehen NICHT literal in den `.bob` (makro-getemplatet) → einzige Quelle ist `pvs_linked`.
- **Generiert** von `ioc-e3/gen_evr_full_db.py` (deterministisch, sortiert, LF): schließt die 9 kuratierten
  (Doppel-Record-Boot-Fehler) + die Lücke aus → 573 − 5 (kuratiert-Overlap) − 1 = **567**. Typ-Heuristik (alle
  boot-bewiesen): `-SP`→`ao` · `-Cmd`→`bo` · `-Sts`→`bi` · `-I`→`longin` · sonst→`ai`. Jeder Record VAL=0,
  PINI=YES, **`ASG(private)` (read-only)**, **keine `info()`-Tags** (Autosave ist info-getrieben → ignoriert sie;
  kein großes `.sav`, kein Boot-Delay). **Regenerieren:**
  `cd EPICS-MCP-Server && uv run python sandbox/ioc-e3/gen_evr_full_db.py`. Unit-Test:
  `tests/test_sandbox_evr_gen.py` (RELATIONEN, nicht die Zahl 567 — eine context-cap-Untergrenze).
- **Reload = Restart** (kein Rebuild): `st.cmd` lädt `fbis-dln01-evr-full.db` als **zweite** `dbLoadRecords`-Zeile;
  `./ioc-e3` ist gemountet → `docker compose -f sandbox/docker-compose.yml restart test-ioc` re-runt `iocsh st.cmd`
  und lädt die neue `.db`. recsync re-announct die 567 nach CF (~15–90 s) → `find_channels("…:*")` ≈ **576**
  (567 + 9 kuratiert; recsync/iocStats-Infra liegt unter dem DASH-Prefix `FBIS-DLN01-Ctrl-EVR-01:` und zählt NICHT
  mit). **Rollback bei Boot-Fehler:** die zweite `dbLoadRecords`-Zeile in `st.cmd` auskommentieren + erneut
  `restart` → zurück auf den 9-Record-Stand (die kuratierte `fbis-dln01-evr.db` bleibt unangetastet = Fallback).
- **⚠️ CF-Cap-Override nötig:** der CF-Checker withheld bei `>= channelfinder_max_results` Kanälen (Default
  **500**) → bei ~576 unter dem Prefix bräche `cf_unregistered` (und der W1-Live-Test). Darum in der Live-Lane
  `EPICS_MCP_CHANNELFINDER_MAX_RESULTS=2000` setzen (`.mcp.json`-Env + `pytest -m live`-Env). Site-Default bleibt
  500.

### Image bauen (einmalig — braucht ESS-Artifactory über den Host-Proxy)

Der Build-Container erreicht ESS-Artifactory NICHT direkt (VPN-Route nur am Host). Darum ein
**Host-CONNECT-Proxy nur während des Builds** (Skript `sandbox/connect_proxy.py`, stdlib):

```powershell
# 1) Proxy am Host starten (erreicht Artifactory via VPN):
python sandbox/connect_proxy.py 8899    # läuft im Hintergrund; nach dem Build beenden (gezielt per PID!)
# 2) Image bauen (conda zieht epics-base+require+essioc aus dem ESS-conda-Channel via Proxy):
docker build --build-arg HTTPS_PROXY=http://host.docker.internal:8899 `
  --build-arg HTTP_PROXY=http://host.docker.internal:8899 `
  -t epics-sandbox-e3-ioc:7.0.9 -f sandbox/ioc-e3/Dockerfile sandbox/ioc-e3
```

Pakete (gemessen): epics-base 7.0.9 + pvxs 1.5 (conda-forge), require 6.0.0 + essioc 2.1.9 + autosave 6.0
+ caputlog 4.1 + iocstats 4.0 + recsync 1.8 (ess-conda-local). Artifactory-Details: [`docs/ess-gitlab-and-datasets.md`](../../docs/ess-gitlab-and-datasets.md) + [`local-services-research/SOURCES-and-artifactory.md`](../../analysis/epics-mcp-daily-work/local-services-research/SOURCES-and-artifactory.md).

## Phase C / C-1 — Archiver Appliance 2.1.1 (`is_archived` / `get_pv_history`)

**ESS-Prod-Stand (decision GR / Option C, P5):** EPICS **Archiver Appliance 2.1.1 + MariaDB + 4-Instanz-Tomcat**
(mgmt 17665 / engine 17666 / etl 17667 / retrieval 17668), 1:1 zu `ics-ans-role-epicsarchiverap @ v2.1.0`.
Löst den vorherigen `pklaus/archiver-appliance`-Bau (2019, Single-JVM, Redis) ab. EINE parametrisierte
Image-Quelle (`archiver/Dockerfile`): WARs aus dem ESS-Release-Artefakt `archappl_v2.1.1.tar.gz` (am **Host**
gezogen via `sandbox/fetch_archiver_artifact.sh` → COPY, weil der Build-Container Artifactory nicht erreicht);
Tomcat **9.0.85** + JDK **21** aus dem offiziellen `tomcat:9.0.85-jre21-temurin-jammy`; Connector/J **5.1.48**
aus Maven Central. Die 4 Webapps bilden EINE Appliance (gemeinsames `ARCHAPPL_MYIDENTITY=appliance0`); nur
**mgmt** bindet den Hazelcast-Cluster-Server (`:16670`), engine/etl/retrieval joinen als Clients → **mgmt
bootet zuletzt**.

**⚠ Zwei MCP-URLs (4-Instanz-Topologie):** `is_archived` trifft **mgmt** (`/mgmt/bpl`, `:17665`),
`get_pv_history` trifft **retrieval** (`/retrieval/data`, `:17668`) — getrennte Tomcats, exakt wie
`appliances.xml` zwei Endpunkte definiert (kein Front-Proxy in der ESS-Rolle). `.mcp.json` (→ **neues
Fenster**): `EPICS_MCP_ARCHIVER_URL=http://localhost:17665` **und**
`EPICS_MCP_ARCHIVER_RETRIEVAL_URL=http://localhost:17668`. (Single-JVM: `RETRIEVAL_URL` leer lassen → Fallback
auf `ARCHIVER_URL`.)

**Vorbereitung (Host, einmalig):** `bash sandbox/fetch_archiver_artifact.sh` (340 MB + sha256). Dann bauen:
`docker compose -f sandbox/docker-compose.yml build archiver-mgmt` (das Image, 4× genutzt).

**Hochfahren (gegated — vorher `docker ps` frisch; `--no-deps` schützt den Bestand):**

```powershell
docker ps                                                                              # frisch (Multi-Window!)
# Reihenfolge: mariadb (DDL-Init) → 3 Clients → mgmt (Cluster-Server, zuletzt):
docker compose -f sandbox/docker-compose.yml up -d --no-deps archiver-mariadb
docker compose -f sandbox/docker-compose.yml up -d --no-deps archiver-engine archiver-etl archiver-retrieval
docker compose -f sandbox/docker-compose.yml up -d --no-deps archiver-mgmt
curl -fs http://localhost:17665/mgmt/bpl/getApplianceInfo                              # appliance up
EPICS-MCP-Server\.venv\Scripts\python.exe sandbox/seed/archive_evr_pvs.py             # 5 EVR-PVs anmelden + pollen
curl -fs "http://localhost:17665/mgmt/bpl/getPVStatus?pv=FBIS-DLN01:Ctrl-EVR-01:12VValue"   # → "Being archived"
curl -fs "http://localhost:17668/retrieval/data/getData.json?pv=FBIS-DLN01:Ctrl-EVR-01:12VValue&from=...&to=..."  # retrieval :17668!
```

**⚠ Das Archiver-Set ist BEWUSST vom CF-Seed entkoppelt** (`seed/archive_evr_pvs.py`): es enthält `3V3Value`
(nie-manuell-CF-geseedet, via recsync registriert) **statt** `CmdRst` — so beweist sich der Archiver-Pfad
unabhängig vom CF-Seed. Der MariaDB-Persistenz-Wechsel verliert eine alte Registrierung → nach jedem
DB-Volume-Wipe `archive_evr_pvs.py` erneut laufen (initdb.d läuft nur bei leerem Volume).

**MCP-Tool-DoD (neues Fenster):** `is_archived("FBIS-DLN01:Ctrl-EVR-01:12VValue")` → `{enabled:true,
archived:true}` (mgmt); `get_pv_history(…, <ISO from>, <ISO to>)` → `total>0`, `val≈12.0` (retrieval :17668).
PIN-AFTER-VERIFY: archiver-Image self-built (Base `@sha256` + Artefakt-/Connector-sha256 im Dockerfile);
`mariadb:10.11` nach Verify `@sha256` pinnen.

## Phase C / C-2 — Phoebus-Alarm-Stack (`is_alarm_configured`)

Vier Container — `alarm-kafka` (`apache/kafka:3.8.0`, **KRaft**, kein Zookeeper) + `alarm-elasticsearch`
(eigener Cluster, Host-Port **9201**) + `alarm-logger` (REST Host-Port **8081**) + `alarm-server` (liest die
Config aus Kafka, watcht PVs via PVA) — plus der Mini-Tree `sandbox/alarm/config.xml` (4 EVR-PVs unter
Config-Name `Accelerator`). Aktiviert das Coverage-Signal `is_alarm_configured` über die Alarm-Logger-REST
`/search/alarm/config`, sobald `EPICS_MCP_ALARM_URL=http://localhost:8081` gesetzt ist (`.mcp.json` → **neues
Fenster**).

**ESS-Prod-Stand (decision GR / Option C, P4 erledigt):** `alarm-server`/`-logger` sind **self-built auf den
ESS-Prod-Deploy-Release 5.0.052** (`ics-ans-alarm-server` host_vars/group_vars @ master; Artefakte
`service-alarm-{server,logger}-5.0.052` in `libs-release-local/org/phoebus/` — der **Prod-Deploy-Pin, NICHT der
neueste Release**, Artifactory führt bis 6.0.001). **ESS stellt kein Docker-Image für den Alarm-Stack bereit**
(Deploy = Ansible/systemd) → Self-Build aus dem Artifactory-Artefakt: am **Host** gezogen
(`sandbox/fetch_alarm_artifacts.sh`, anon, kein Token/Proxy) + per `COPY` in den Build (der Container-Egress
erreicht Artifactory NICHT). `alarm-elasticsearch` = **8.5.3** (ESS-Pin ist **8.2.3**, aber auf diesem
cgroup-v2-Dev-Host nicht lauffähig: das in 8.2.3 **und** 8.4.3 gebündelte JDK 18.0.x crasht beim cgroup-v2-Memory-
Read [`CgroupInfo.getMountPoint()` NPE, JDK-8281571; 3 Fix-Versuche erfolglos]; **8.5.3** = erste ES-Linie mit
cgroup-v2-fähigem JDK 19 → die **8.2.x-nächste host-lauffähige** Version — **bewusster, host-bedingter
Fidelity-Caveat**, decision GR/Option C). Funktional neutral: 5.0.052 nutzt den neuen `co.elastic.clients`-ES-8-
Client (`elasticsearch-java:8.2.0`), wire-kompatibel über die GANZE ES-8.x-Linie (der ES-8-Client-BLOCKER
CSS #2273 ist quellcode-tot — `RestHighLevelClient` = 0 Treffer am Tag `ESS-5.0.052`).
**Bewusste Abweichungen:** `alarm-kafka` bleibt `apache/kafka:3.8.0` (KRaft) = REST-gleichwertige
Sandbox-Vereinfachung (ESS-Prod = `ics-ans-role-kafka`, Confluent + ZooKeeper), NICHT „kein 3.6.2-Image";
`alarm-server -server` via CLI statt `settings.ini` = parser-äquivalente Vereinfachung.
**Quell-Referenz (Tag `ESS-5.0.052`):** Logger = `services/alarm-logger/src/main/java/org/phoebus/alarm/logging/`,
Server = `services/alarm-server/src/main/java/org/phoebus/applications/alarm/server/`.

**⚠ ZWINGENDE Reihenfolge (zwei Fallen, beide P4 live erlebt):** **(1) Topics VOR dem Logger anlegen** — startet
der Logger, bevor `Accelerator`/`AcceleratorCommand` existieren, schaltet seine Kafka-Streams-App mit
`MissingSourceTopicException → SHUTDOWN_CLIENT` ab (der REST-Container bleibt „healthy", indexiert aber **nichts**;
auto-create allein hilft nicht, weil die Topics erst entstehen, wenn Server/Import Kafka berühren — zu spät).
**(2) Config-Import NACH** Topics + Logger (sonst landet die Config in Kafka, aber nie im ES-Config-Index → REST
dauerhaft leer). Der Config-Topic `Accelerator` ist **log-compacted** (Phoebus-Konvention).

**Build (P4 — einmalig; vorher die Artefakte am Host ziehen):**

```bash
bash sandbox/fetch_alarm_artifacts.sh                                                   # 190 MB → Build-Kontexte + sha256
MSYS_NO_PATHCONV=1 docker compose -f sandbox/docker-compose.yml build alarm-server alarm-logger   # self-built 5.0.052 (COPY, kein Proxy)
```

**⚠ Migration 8.18 → 8.5.3 (ES-Downgrade + Kafka-Offset-Falle):** ein reiner ES-Wipe re-indexiert NICHT (der
Kafka-Streams-Consumer behält committed Offsets) → **beide** Volumes wipen, sonst bleibt der ES-Config-Index leer
und die REST liefert still `false`. Erst `rm -sf` (ein bloßer Stop hält das Volume), dann `volume rm`:

```bash
MSYS_NO_PATHCONV=1 docker compose -f sandbox/docker-compose.yml rm -sf --stop alarm-server alarm-logger alarm-elasticsearch alarm-kafka
docker volume rm sandbox_alarm-es-data sandbox_alarm-kafka-data
```

**Hochfahren (gegated — vorher `docker ps` frisch):**

```powershell
docker ps                                                                              # frisch (Multi-Window!)
# 1. Kafka + ES hoch
docker compose -f sandbox/docker-compose.yml up -d --no-deps alarm-kafka alarm-elasticsearch
# 2. Topics VOR dem Logger anlegen (Falle 1; Config-Topic Accelerator = compacted):
$K = "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --partitions 1 --replication-factor 1"
docker exec epics-sandbox-alarm-kafka sh -c "$K --topic Accelerator --config cleanup.policy=compact"
docker exec epics-sandbox-alarm-kafka sh -c "$K --topic AcceleratorCommand"
docker exec epics-sandbox-alarm-kafka sh -c "$K --topic AcceleratorTalk"
# 3. Logger + Server hoch (Topics existieren → Streams starten sauber)
docker compose -f sandbox/docker-compose.yml up -d --no-deps alarm-logger alarm-server
# 4. Config EINMALIG importieren (bare Jar via WORKDIR):
docker compose -f sandbox/docker-compose.yml run --rm --no-deps alarm-server `
  /bin/bash -c "java -jar service-alarm-server-5.0.052.jar -config Accelerator -import /config/config.xml -server alarm-kafka:9092 -noshell"
# Config im ES-Index gelandet? (Logger ~15-50 s nach Import). Falls der Logger doch vor den Topics startete und
# seine Streams abschaltete (SHUTDOWN_CLIENT): `docker restart epics-sandbox-alarm-logger` → konsumiert von earliest.
curl -fs "http://localhost:8081/search/alarm/config?config=/Accelerator/*FBIS-DLN01:Ctrl-EVR-01:12VValue"
```

**Verifikation (DoD, neues Fenster):** `is_alarm_configured("FBIS-DLN01:Ctrl-EVR-01:12VValue")` →
`{enabled:true, configured:true}`; `is_alarm_configured("FBIS-DLN01:Ctrl-EVR-01:DlyGen0Prescaler-SP")` →
`{configured:false}` (Negativ-Beweis = die bewusst injizierte Lücke, NICHT im Tree). Offline-Regression
`tests/test_alarm.py`; optionaler Live-Test hinter `EPICS_SANDBOX_ALARM=1`. ⚠ `/search/alarm/config` ist ein
Config-**Change**-Log — ein Treffer beweist Konfiguration; ein Leertreffer ist nur dann ein echtes „nein",
wenn der Logger beim Import lief (sonst withheld).

## Tier 3 — Mock-Naming (opt-in — `diagnose_connection`-Cause-Baum live)

Ein winziges **read-only Test-Double** der ESS-Naming-REST-API (`mock-naming/server.py`, `stdlib
http.server`, ~45 Z.). Es bedient exakt das, was `epics_pv_mcp.services.naming_client` braucht, damit
`diagnose_connection` seine drei Naming-abhängigen Zweige **live** beweisen kann — ohne lokales Naming
kollabieren sie sonst alle auf `indeterminate`. **Kein ESS-Egress, kein Auth, kein Write.** Opt-in via
compose-Profil `naming` → ein plain `docker compose up -d` startet ihn **nicht**.

**Was live prüfbar wird (Cause-Mapping):**

| PV | `_device_name` | Mock | CF | → `likely_cause` |
|---|---|---|---|---|
| `…:EVR-01:DlyGen0Prescaler-SP` (die W2-Lücke) | `FBIS-DLN01:Ctrl-EVR-01` | **200 ACTIVE** | miss | **`unregistered`** |
| `WRONG-DLN99:Ctrl-EVR-01:12VValue` | `WRONG-DLN99:Ctrl-EVR-01` | **404** | miss | **`name_typo`** |
| die W2-Lücke + Naming an **toter URL** | — | connection-refused | miss | **`indeterminate`, `withheld=[naming]`** |

**Bauen + starten (gegated — Container-Lifecycle, vorher `docker ps` frisch):** Das Profil ist
**additiv** → nur der Mock entsteht, der laufende Stack bleibt unberührt.

```bash
docker ps                                                                          # frisch (Multi-Window!)
docker compose -f sandbox/docker-compose.yml --profile naming up -d --build mock-naming
# Smoke:
curl -s   127.0.0.1:8099/rest/deviceNames/FBIS-DLN01:Ctrl-EVR-01                   # → {"status":"ACTIVE",...}
curl -s -o /dev/null -w "%{http_code}" 127.0.0.1:8099/rest/deviceNames/WRONG-DLN99:Ctrl-EVR-01   # → 404
curl -sI  127.0.0.1:8099/                                                          # → 200 (HEAD = check_connectivity)
```

**Naming-Live-Lane (die drei Tests monkeypatchen `EPICS_MCP_NAMING_URL` selbst — nicht ambient setzen):**

```bash
EPICS_SANDBOX=1 EPICS_SANDBOX_CF=1 EPICS_SANDBOX_NAMING=1 \
EPICS_MCP_PROVIDER=pva EPICS_PVA_NAME_SERVERS=127.0.0.1:5075 \
EPICS_PVA_AUTO_ADDR_LIST=NO EPICS_PVA_ADDR_LIST=127.0.0.1 \
EPICS_MCP_CHANNELFINDER_URL=http://localhost:8080/ChannelFinder \
uv run pytest -m live -k diagnose
# → L1-L6 grün + L7 unregistered, L8 name_typo, L9 withheld grün.
```

> ⚠️ **Trailing-Slash PFLICHT** bei `EPICS_MCP_NAMING_URL=http://localhost:8099/` — der Client concatet
> `base_url + "rest/deviceNames/"`; ohne den Slash bräche der Pfad. Die Var ist in
> [`.env.example`](../.env.example) dokumentiert (Default **leer = disabled**, kein ESS-Egress);
> **`.mcp.json` bleibt unverändert** (Default leer).
>
> **Isolation (§8):** Der Server bindet **container-intern `0.0.0.0`** (Bridge-/Publish-erreichbar); die
> Host-Isolation macht der **`127.0.0.1:8099`-Publish** in compose — kein `0.0.0.0`-Host-Bind, kein
> `internal:` (dieselbe Lehre wie beim IOC-INTF).

## Hochfahren

```powershell
docker ps                                                           # frisch prüfen (Multi-Window!)
docker compose -f sandbox/docker-compose.yml up -d test-ioc         # e3-IOC
```

## Netzwerk-Befund (wichtig)

Auf Docker-Desktop/WSL2 erreicht der **native Windows-MCP** das containerisierte IOC über **PVA**
(name-server-TCP, PVXS↔PVXS, eine wiederverwendete Verbindung) — **CA NICHT** (CA wählt nach der Suche
eine separate Verbindung zur Container-IP → NAT-Timeout). → **PVA ist der Weg.**

## Aktivierung im MCP (`.mcp.json` → `mcpServers.epics-pv.env`)

stdio-MCP liest Env **nur beim Start** → wirkt erst im **neuen Claude-Fenster**. `EPICS_*_NAME_SERVERS`/
`*_ADDR_LIST` sind **Standard-EPICS-Env** (p4p/PVXS liest sie), `EPICS_MCP_PROVIDER` ist Config.

| Feld | Wert |
|---|---|
| `EPICS_MCP_PROVIDER` | `pva` |
| `EPICS_PVA_NAME_SERVERS` | `127.0.0.1:5075` |
| `EPICS_MCP_ALLOW_PV_WRITE` | `true` (scoped Write-Ausnahme — s. u.) |
| `EPICS_MCP_PV_WRITE_PATTERN` | `^FBIS-DLN01:Ctrl-EVR-01:(Temp1ThrUpCrt-SP\|CmdRst)$` |
| `EPICS_MCP_CHANNELFINDER_MAX_RESULTS` | `2000` (hebt den CF-Cap für das ~576-Kanal-EVR-Prefix; Default 500 site-sicher — sonst withholdet der CF-Checker → `cf_unregistered`/W1/W2 brechen mit „len 0") |

> ⚠️ `provider` ist EXKLUSIV (ca↔pva) → betrifft alle Fenster beim nächsten epics-pv-Start (Dirk OK 2026-06-28).
>
> ⚠️ **Scoped Write-Ausnahme:** `set_pv_value` ist NUR für die 2 Schreibziele `Temp1ThrUpCrt-SP`/`CmdRst`
> freigeschaltet (Regex-Allowlist + Rate-Limit + Audit; `ASG(private)` schützt die 7 Readbacks am IOC).
> **Default überall sonst bleibt read-only/write-gated.** Allowlist und `.db`-ASG-Verteilung sind
> deckungsgleich gepinnt durch `tests/test_sandbox_db_asg.py`.

## Verifikation

- **In-window (Dev-Loop, kein Fenster-Neustart):** Shell-Env (`EPICS_MCP_PROVIDER=pva`,
  `EPICS_PVA_NAME_SERVERS=127.0.0.1:5075`), dann im MCP-venv
  `python -c "import asyncio; from epics_pv_mcp.services.epics_client import pv_get; print(asyncio.run(pv_get('FBIS-DLN01:Ctrl-EVR-01:12VValue')))"`
  → `value: 12.0` + NT display (units V).
- **Regression:** `EPICS_SANDBOX=1 EPICS_MCP_PROVIDER=pva EPICS_PVA_NAME_SERVERS=127.0.0.1:5075 EPICS_PVA_AUTO_ADDR_LIST=NO EPICS_PVA_ADDR_LIST=127.0.0.1 uv run pytest -m live`.
- **Finale MCP-Tool-DoD (frisches Fenster):** `mcp__epics-pv__get_pv_value("FBIS-DLN01:Ctrl-EVR-01:12VValue")`;
  nach Phase B `find_channels(...)` / `find_device(...)`.
- **⚠ CI-Caveat — die ESS-Treue lebt NUR lokal:** Die `-m live`-Tests laufen ausschließlich gegen diese
  laufende Sandbox; GitHub-CI fährt `pytest -m "not live"` und **überspringt** sie. CI beweist damit die
  Funktions-Logik der Reader (ChannelFinder-/Archiver-/Alarm-Parsing), **nicht**, dass sie gegen die
  ESS-Prod-Versionen (CF 4.7.3, Archiver 2.1.1, Alarm 5.0.052, ES 8.11.3/8.5.3) korrekt verdrahtet sind —
  diese Treue wird einzig hier, lokal, gegen den realen Stack re-verifiziert. Zuletzt **2026-06-30 (GR-Abschluss):**
  alle live-relevanten epics-pv-Tools grün, inkl. `get_pv_history`→retrieval:17668 end-to-end (`val=12`).

## Herunterfahren

```powershell
docker compose -f sandbox/docker-compose.yml down   # = Prozess-Stopp -> Dirks OK + docker ps frisch
```
