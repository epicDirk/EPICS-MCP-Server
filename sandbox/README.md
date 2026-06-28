# Lokale EPICS-Service-Sandbox

Lokale Services in Docker, gelesen vom **read-only** `epics-pv`-MCP gegen echte Services — **ohne**
ESS-Produktion (VPN-gated). ⚠️ **Netzwerk ehrlich:** die Docker-Ports binden **`0.0.0.0`/`[::]`**
(WSL2-NAT-Erfordernis, s. „Netzwerk-Befund" unten) → die Sandbox-PVs sind im **LAN erreichbar** (für ein
lokales Test-/Sim-IOC akzeptabel). Die **MCP-seitige** `127.0.0.1`-Isolation (addr-list) bleibt davon
**unberührt** — der MCP erreicht ESS-Produktion NICHT. Zur **Laufzeit kein ESS-Kontakt** (nur der einmalige
Image-Build zieht e3-Pakete, s. u.).

## Komponenten

| Service | Was | Ports (host) |
|---|---|---|
| **`test-ioc`** | echtes **e3-IOC** (`require essioc`), Gerät `FBIS-DLN01:Ctrl-EVR-01`, serviert die `.db` über CA+PVA (QSRV2) | 5064/5065 (CA), 5075 (PVA) |
| `elasticsearch` (**Phase B, geplant**) | Backend für ChannelFinder | 9200 |
| `channelfinder` + `recceiver` (**Phase B, geplant**) | PV-Verzeichnis; reccaster (in essioc) → recceiver → CF (Auto-Populate, container-to-container) | 8080 |

## Das e3-Test-IOC (`ioc-e3/`)

**Echtes e3, nicht „softIocPVX + lose .db":** `st.cmd` macht `require essioc` + `iocshLoad
common_config.iocsh` → lädt autosave/caputlog/iocStats/recsync/access-security; `dbLoadRecords` lädt
`fbis-dln01-evr.db` (9 Records: 2 mbbi/1 bi/3 ai/1 ao/1 calc/1 bo mit EGU/Limits/Alarm/DESC, ESS-Namens-
konvention `Sec-Sub:Dis-Dev-Idx:Signal`; Signal-Namen aus dem BIS-Dataset EVR-AMC slot2). **`iocsh` wrappt
`softIocPVX`** → CA + PVA (QSRV2).

> **Ehrliche Einordnung:** Dies ist ein **lokales Test-/Sim-IOC**, KEIN Komitee-Artefakt und KEIN echtes
> mrfioc2-EVR-IOC — in Produktion liefert das mrfioc2-Modul die EVR-PVs; hier sind es Soft-Records mit
> ESS-konformen Namen/Feldern, damit der MCP gegen realistische ESS-PVs testet.

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

> ⚠️ `provider` ist EXKLUSIV (ca↔pva) → betrifft alle Fenster beim nächsten epics-pv-Start (Dirk OK 2026-06-28).

## Verifikation

- **In-window (Dev-Loop, kein Fenster-Neustart):** Shell-Env (`EPICS_MCP_PROVIDER=pva`,
  `EPICS_PVA_NAME_SERVERS=127.0.0.1:5075`), dann im MCP-venv
  `python -c "import asyncio; from epics_pv_mcp.services.epics_client import pv_get; print(asyncio.run(pv_get('FBIS-DLN01:Ctrl-EVR-01:12VValue')))"`
  → `value: 12.0` + NT display (units V).
- **Regression:** `EPICS_SANDBOX=1 EPICS_MCP_PROVIDER=pva EPICS_PVA_NAME_SERVERS=127.0.0.1:5075 uv run pytest -m live`.
- **Finale MCP-Tool-DoD (frisches Fenster):** `mcp__epics-pv__get_pv_value("FBIS-DLN01:Ctrl-EVR-01:12VValue")`;
  nach Phase B `find_channels(...)` / `find_device(...)`.

## Herunterfahren

```powershell
docker compose -f sandbox/docker-compose.yml down   # = Prozess-Stopp -> Dirks OK + docker ps frisch
```
