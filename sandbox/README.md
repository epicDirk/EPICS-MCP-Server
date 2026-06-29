# Lokale EPICS-Service-Sandbox

Lokale Services in Docker, gelesen vom **read-only** `epics-pv`-MCP gegen echte Services — **ohne**
ESS-Produktion (VPN-gated). ⚠️ **Netzwerk ehrlich:** die Docker-Ports binden **`0.0.0.0`/`[::]`**
(WSL2-NAT-Erfordernis, s. „Netzwerk-Befund" unten) → die Sandbox-PVs sind im **LAN erreichbar** (für ein
lokales Test-/Sim-IOC akzeptabel). **Schreib-Asymmetrie ehrlich:** die 7 Readbacks tragen
`field(ASG,"private")` (LAN-**lesbar**, am IOC read-only), aber die 2 ASG-DEFAULT-Records
`Temp1ThrUpCrt-SP`/`CmdRst` sind von **jedem LAN-Host SCHREIBBAR** (`asCheckClientIP` filtert sie nicht).
Die **MCP-seitige** `127.0.0.1`-Isolation (addr-list) bleibt davon **unberührt** — der MCP erreicht
ESS-Produktion NICHT. Zur **Laufzeit kein ESS-Kontakt** (nur der einmalige Image-Build zieht e3-Pakete, s. u.).

## Komponenten

| Service | Was | Ports (host) |
|---|---|---|
| **`test-ioc`** | echtes **e3-IOC** (`require essioc`), Gerät `FBIS-DLN01:Ctrl-EVR-01`, serviert die `.db` über CA+PVA (QSRV2) | 5064/5065 (CA), 5075 (PVA) |
| **`elasticsearch`** (**Phase B / M1 — da**) | Backend für ChannelFinder (`:8.18.0`, single-node, xpack-security off) | 9200 |
| **`channelfinder`** (**Phase B / M1 — da**) | PV-Verzeichnis (REST), `ghcr.io/channelfinder/channelfinderservice:ChannelFinder-5.1.0`; API nativ unter `/ChannelFinder/resources/…` | 8080 |
| **`recceiver`** (**Phase B / M2 — LIVE**) | vanilla recsync 1.8 (ohne Patches); empfängt die reccaster-Records des `test-ioc` → schreibt sie auto nach CF (essioc→reccaster→recceiver→CF) | — (container-intern, UDP 5049) |
| **`archiver`** (**Phase C / C-1 — LIVE**) | EPICS Archiver Appliance (`pklaus/archiver-appliance`, single-JVM, Redis-Persistence statt MariaDB); archiviert die `test-ioc`-PVs **per CA über die Bridge** → aktiviert `is_archived`/`get_pv_history` | 17665 |
| **`archiver-redis`** (**Phase C / C-1**) | Config-Persistenz des Archivers (ersetzt MariaDB) | — (container-intern, 6379) |

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
im `test-ioc` lauscht auf `0.0.0.0:5049`; der **recceiver** (`sandbox/recceiver/`, **vanilla recsync 1.8 ohne
Patches**) sendet alle 15 s einen UDP-Broadcast (`255.255.255.255:5049`, subnetz-unabhängig); der reccaster
verbindet sich per UDP-Quell-IP zurück und überträgt seine Records. Die CF-Verbindung kommt aus
**`channelfinderapi.conf`** (`[DEFAULT] BaseURL=http://channelfinder:8080/ChannelFinder`, `admin/adminPass`) —
recsync-`cfstore` ruft `ChannelFinderClient()` ohne Args, pyCFClient (v3.0.0) liest die conf aus `/etc` ODER dem
cwd. `docker.conf` `[cf]` setzt alias/recordType/recordDesc + `cleanOnStart` + festen `recceiverId=recsync-sandbox`
(so inaktiviert das Clean NUR die recceiver-eigenen Kanäle; die admin-geseedeten M1-Kanäle bleiben unberührt).

**recceiver bauen + starten (gegated — Container-Lifecycle, vorher `docker ps`):**

```powershell
docker compose -f sandbox/docker-compose.yml build recceiver   # Egress github.com+pypi.org (direkt; bei Block:
                                                               # HTTPS_PROXY/HTTP_PROXY-Env → build.args, wie ioc-e3)
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

## Phase C / C-1 — Archiver Appliance (`is_archived` / `get_pv_history`)

Lokale **EPICS Archiver Appliance** (`pklaus/archiver-appliance`, single-JVM, **Redis**-Persistence statt
MariaDB) auf `:17665`. Der MCP-Client (`archiver_client.py`) + die Tools `is_archived`/`get_pv_history`
existieren bereits — sie „leuchten auf", sobald `EPICS_MCP_ARCHIVER_URL=http://localhost:17665` gesetzt ist
(`.mcp.json` → **neues Fenster**). Die Archiver-Engine ist **CA-nativ** (2019er Build) und erreicht das
`test-ioc` **per CA über die Bridge** (Container→Container; der WSL2-NAT-Befund unten betrifft NUR
Host-Windows→Container) — live verifiziert (`connectionState:true`).

**Hochfahren (gegated — vorher `docker ps` frisch):**

```powershell
docker ps                                                                              # frisch (Multi-Window!)
docker compose -f sandbox/docker-compose.yml up -d --no-deps archiver-redis archiver   # --no-deps: Bestand unberührt
# ~1-2 Min Anlauf (4 Webapps in einem Tomcat), dann:
curl -fs http://localhost:17665/mgmt/bpl/getApplianceInfo                              # appliance up
EPICS-MCP-Server\.venv\Scripts\python.exe sandbox/seed/archive_evr_pvs.py             # 5 EVR-PVs anmelden + pollen
# Status-Reise: "Appliance assigned" -> (Initial sampling, paar Min) -> "Being archived":
curl -fs "http://localhost:17665/mgmt/bpl/getPVStatus?pv=FBIS-DLN01:Ctrl-EVR-01:12VValue"
```

**⚠ Das Archiver-Set ist BEWUSST vom CF-Seed entkoppelt** (`seed/archive_evr_pvs.py`): es enthält `3V3Value`
(nie-manuell-CF-geseedet, via recsync registriert) **statt** `CmdRst` — so beweist sich der Archiver-Pfad
unabhängig vom CF-Seed.

**Verifikation (live bestätigt 2026-06-29):** alle 5 EVR-PVs (`12VValue`/`Temp1Value`/`EvtACnt-I`/`3V3Value`/
`BMod`) → `Being archived`; `getData.json` 12VValue → `val=12.0` (EGU V, PREC 2). Beide Images digest-gepinnt
nach Verify. **MCP-Tool-DoD (neues Fenster):** `is_archived("FBIS-DLN01:Ctrl-EVR-01:12VValue")` →
`{enabled:true, archived:true}`; `get_pv_history(…, <ISO from>, <ISO to>)` → `total>0`, `val≈12.0`. Optionaler
Live-Test hinter `EPICS_SANDBOX_ARCHIVER=1`.

## Phase C / C-2 — Phoebus-Alarm-Stack (`is_alarm_configured`)

Vier Container — `alarm-kafka` (`apache/kafka:3.8.0`, **KRaft**, kein Zookeeper) + `alarm-elasticsearch`
(eigener Cluster, Host-Port **9201**) + `alarm-logger` (REST Host-Port **8081**) + `alarm-server` (liest die
Config aus Kafka, watcht PVs via PVA) — plus der Mini-Tree `sandbox/alarm/config.xml` (4 EVR-PVs unter
Config-Name `Accelerator`). Aktiviert das Coverage-Signal `is_alarm_configured` über die Alarm-Logger-REST
`/search/alarm/config`, sobald `EPICS_MCP_ALARM_URL=http://localhost:8081` gesetzt ist (`.mcp.json` → **neues
Fenster**). Upstream-Phoebus-`:master`-Images (ESS stellt kein eigenes Deploy-Image bereit, nur einen
Maven-Wrapper → Upstream ist hier der Kanon).

**⚠ Import-Reihenfolge ZWINGEND** (sonst landet die Config in Kafka, aber nie im ES-Config-Index → die REST
liefert dauerhaft leer, obwohl konfiguriert): erst Kafka + Logger hoch (Logger subscribed den Config-Topic),
**DANN** der Config-Import.

**Hochfahren (gegated — vorher `docker ps` frisch):**

```powershell
docker ps                                                                              # frisch (Multi-Window!)
docker compose -f sandbox/docker-compose.yml up -d --no-deps alarm-kafka alarm-elasticsearch alarm-logger alarm-server
# ~1-2 Min Anlauf (Kafka + ES + 2 JVMs), dann die Config EINMALIG importieren:
docker compose -f sandbox/docker-compose.yml run --rm --no-deps alarm-server `
  /bin/bash -c "java -jar /alarmserver/service-alarm-server-*.jar -config Accelerator -import /config/config.xml -server alarm-kafka:9092"
# Config im ES-Index gelandet? (Logger ~15 s nach Import):
curl -fs "http://localhost:8081/search/alarm/config?config=/Accelerator/*FBIS-DLN01:Ctrl-EVR-01:12VValue"
```

**Verifikation (DoD, neues Fenster):** `is_alarm_configured("FBIS-DLN01:Ctrl-EVR-01:12VValue")` →
`{enabled:true, configured:true}`; `is_alarm_configured("FBIS-DLN01:Ctrl-EVR-01:DlyGen0Prescaler-SP")` →
`{configured:false}` (Negativ-Beweis = die bewusst injizierte Lücke, NICHT im Tree). Offline-Regression
`tests/test_alarm.py`; optionaler Live-Test hinter `EPICS_SANDBOX_ALARM=1`. ⚠ `/search/alarm/config` ist ein
Config-**Change**-Log — ein Treffer beweist Konfiguration; ein Leertreffer ist nur dann ein echtes „nein",
wenn der Logger beim Import lief (sonst withheld).

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

## Herunterfahren

```powershell
docker compose -f sandbox/docker-compose.yml down   # = Prozess-Stopp -> Dirks OK + docker ps frisch
```
