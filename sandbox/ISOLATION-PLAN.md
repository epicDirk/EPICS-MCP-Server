# Sandbox-Netz-Isolation — Runbook (kein Rausfunken / nicht vom ESS-LAN erreichbar)

> **Zweck:** Die lokale EPICS-Docker-Sandbox darf **keine Signale ins ESS-Netz senden** und **nicht vom
> ESS-LAN erreichbar** sein — soll aber lokal voll zum Testen des `epics-pv`-MCP nutzbar bleiben.
> **Status: auditiert + Fix BEWIESEN, Anwenden GATED.** Decision **GW** (2026-06-30).
> **Anwenden ERST NACH dem GR-Abschluss** (Voll-Stack-Recreate; Dirks `docker compose up`-OK).
> Quelle: 2 read-only No-Emit-Multi-Agent-Audits (kein Paket Richtung ESS).

---

## 1. Befund (warum das nötig ist)

**Outbound HEUTE = nein** (auditiert, nicht angenommen):
- Alle 13 Container hängen an **einem** Bridge `sandbox_channelfinder-net` (`172.21.0.0/16`), je nur `lo`+`eth0`,
  kein Container dual-homed, **kein** `network_mode: host`, **kein** `macvlan` (grep = 0 Treffer).
- `/proc/net/tcp(+6)` aller 13 Container dekodiert → **jede** offene Verbindung ist `172.21.*` oder Loopback
  (das erwartete Mesh: IOC↔Archiver/Alarm CA, CF↔ES, Alarm↔Kafka, Archiver↔MariaDB). Null Off-Bridge-Peers.
- EPICS-Clients eng gebunden: Archiver `EPICS_CA_ADDR_LIST=epics-sandbox-test-ioc` (`AUTO=no`), Alarm
  `EPICS_PVA_NAME_SERVERS=epics-sandbox-test-ioc:5075` (`AUTO=NO`).
- Broadcasts/Beacons bleiben im Bridge-L2: recceiver `255.255.255.255:5049` (Limited Broadcast, RFC 919/922 — nie
  geroutet), CA/PVA-Beacon → `172.21.255.255` (Gateway forwardet nicht off-link), PVA-Multicast `224.0.0.128`
  (link-local, Router dürfen nicht forwarden).

**ABER nicht air-gapped** (= warum wir handeln müssen):
- Der Bridge ist **`internal: false`** → jeder Container hat eine **Default-Route** → `172.21.0.1` → docker-desktop-VM
  → gvisor `192.168.65.1` → **Windows-Host** → ESS-Gateway `172.18.23.254`.
- Der Host sitzt **direkt im ESS-LAN** (`172.18.23.209/22`, GW `.254`, DNS-Suffix `esss.lu.se`/`ess.eu`) — **kein VPN**.
- Ein Prozess, der **aktiv** eine ESS-/Internet-IP anwählt (Fehlkonfig einer addr-list, Phone-home), würde via NAT raus.

**Inbound = offen:** 10 published Ports binden `0.0.0.0` → vom ESS-LAN über die Host-IP erreichbar (2 IOC-Records
laut README sogar LAN-schreibbar).

> ⚠️ Falle: `172.18.*` ist **nur am Windows-Host** das ESS-LAN. *Innerhalb* Docker ist `172.18.0.0/16` ein lokaler
> Bridge (`claude-memory-mcp_default`) — kein Sandbox-Container fasst ihn an. ESS-Reach beurteilt sich auf Host-Ebene.

---

## 2. Der Fix (zwei Compose-Änderungen, bewiesen)

Beide auf Wegwerf-`egresstest-`-Ressourcen verifiziert — **bricht das lokale Testen NICHT**:

| Änderung | Wirkung | Beweis |
|---|---|---|
| **`internal: true`** auf `channelfinder-net` | Container bekommen **keine** Default-Route → Egress nach ESS/Internet **baulich unmöglich** | Wegwerf-`--internal`-Netz: `ip route` = nur Link-Route, **kein default** |
| **Alle Ports auf `127.0.0.1` binden** | Schließt die Inbound-LAN-Exposition (nur Windows-Loopback erreicht sie) | Wegwerf-Container `127.0.0.1:5099` → Host-`curl` = **HTTP 200** |

**Warum es lokal weiter funktioniert:** `internal:true` blockt nur Container→außen; Host→Container-Publishing bleibt
(bewiesen), das interne Mesh ist sowieso bridge-intern, der MCP liest über `127.0.0.1`-Ports. **Build-Zeit-Proxy**
(`HTTPS_PROXY` Build-Args) ist `docker build` ≠ Runtime → unberührt. **Die README-Notiz „0.0.0.0 ist WSL2-Pflicht"
ist widerlegt** (127.0.0.1-Bind ist vom Host erreichbar).

### Exakte Edits in `docker-compose.yml`

> Zeilennummern sind ein Stand vom 2026-06-30 (können driften) — im Zweifel über den **String** matchen, nicht die Zeile.

**(a) Ports auf Loopback** — jeweils `"127.0.0.1:"` voranstellen:

```
"5064:5064"     → "127.0.0.1:5064:5064"        # IOC CA            (~L37)
"5064:5064/udp" → "127.0.0.1:5064:5064/udp"    # IOC CA search     (~L38)
"5065:5065/udp" → "127.0.0.1:5065:5065/udp"    # IOC CA beacon     (~L39)
"5075:5075"     → "127.0.0.1:5075:5075"        # IOC PVA   (MCP)   (~L40)
"9200:9200"     → "127.0.0.1:9200:9200"        # CF-ES (debug)     (~L75)
"8080:8080"     → "127.0.0.1:8080:8080"        # ChannelFinder (MCP) (~L113)
"17668:17668"   → "127.0.0.1:17668:17668"      # Archiver retrieval (MCP) (~L276)
"17665:17665"   → "127.0.0.1:17665:17665"      # Archiver mgmt (MCP) (~L317)
"9201:9200"     → "127.0.0.1:9201:9200"        # Alarm-ES (debug)  (~L402)
"8081:8080"     → "127.0.0.1:8081:8080"        # Alarm-Logger (MCP) (~L434)
```
(+ den irreführenden Kommentar bei ~L36 entfernen, der den `127.0.0.1:`-Prefix verbietet.)

**(b) Netz air-gappen** — eine Zeile ergänzen (~L480–481):

```yaml
networks:
  channelfinder-net:
    driver: bridge
    internal: true        # ← neu: kein Egress (keine Default-Route in den Containern)
```

---

## 3. Anwenden (gegated — ERST nach dem GR-Abschluss, mit Dirks OK)

```powershell
docker ps                                                        # frisch prüfen (Multi-Window!) — kein anderes Fenster aktiv?
# Edits in docker-compose.yml speichern, dann EINMAL die GANZE Sandbox neu erzeugen
# (Netzwechsel = Full-Recreate, NICHT --no-deps; Volumes/Daten überleben):
docker compose -f EPICS-MCP-Server/sandbox/docker-compose.yml up -d
```

> ⚠️ **Full-Stack-Recreate**, weil sich das Netz selbst ändert. Genau **deshalb erst nach P5/Abschluss** — sonst
> kollidiert es mit dem Archiver-Setup. Nach dem Recreate ggf. Archiver-Re-Seed (`seed/archive_evr_pvs.py`) prüfen,
> falls das MariaDB-Volume betroffen war.

---

## 4. Verifikation (nach dem Recreate)

- **Lokal funktioniert noch:** `mcp__epics-pv__get_pv_value("FBIS-DLN01:Ctrl-EVR-01:12VValue")` → 12.0 ·
  CF/Archiver/Alarm-curls auf `127.0.0.1:8080|17665|17668|8081` → 200 · `find_channels` 576 · `coverage_audit` 572/1.
- **Egress ist zu (bewiesen-Muster):** `docker exec epics-sandbox-test-ioc sh -c 'cat /proc/net/route'` → **keine**
  Default-Route mehr (nur die `172.21.0.0/16`-Link-Route). (Minimal-Images haben kein `ip`; `/proc/net/route` lesen.)
- **Inbound ist zu:** `docker port epics-sandbox-test-ioc` → Bindings zeigen `127.0.0.1:…` statt `0.0.0.0:…`.

---

## 5. Rollback

- Compose-Edits zurücknehmen (git) + `docker compose … up -d` → zurück auf `0.0.0.0` + `internal:false`.
- Sollte ein Service Runtime-Egress brauchen (heute keiner), reicht es, NUR `internal:true` zu entfernen und die
  127.0.0.1-Binds zu behalten (Inbound-Schutz ohne Egress-Block).

---

## 6. README-Korrekturen (Teil des Anwendens)

Nach dem Recreate die jetzt **veralteten** Aussagen in `sandbox/README.md` richtigstellen:
- **„Netzwerk-Befund"/„Netzwerk ehrlich":** Die Ports binden **nicht mehr** `0.0.0.0` (→ `127.0.0.1`), die Sandbox ist
  **nicht mehr LAN-erreichbar**, und der Bridge ist `internal` (kein Egress). Die Behauptung „0.0.0.0 ist WSL2-NAT-
  Erfordernis" ist **widerlegt** und zu streichen.
- Den Hinweis ergänzen, dass `set_pv_value` (scoped) jetzt nur noch über Host-Loopback erreichbar ist.

---

## 7. Optionale Defense-in-Depth (billig, latente Risiken)

- **B — EPICS-addr-list-Hygiene am IOC:** `EPICS_CAS_BEACON_ADDR_LIST`/`EPICS_PVAS_BEACON_ADDR_LIST` auf den Bridge
  scopen, `RECCEIVER_ADDRLIST` von `255.255.255.255:5049` auf den IOC-Namen — macht „durch's Netz dicht" zu „explizit
  dicht". (Heute nur latent.)
- **C — Windows-Defender-Firewall-Outbound-Regel** (WSL/Docker-Subnetz → `172.18.0.0/16` blocken). OS-Backstop,
  überlebt sogar einen Compose-Fehler — aber am gröbsten; nur wenn ein harter, docker-unabhängiger Riegel gewünscht ist.

---

## 8. Stehende Invariante (für jede künftige Sandbox-Änderung)

Die Isolation ist ab Anwenden eine **Invariante**: jede künftige Compose-/Netz-Änderung MUSS sie erhalten —
**kein** `network_mode: host`, **kein** `macvlan`/`ipvlan` auf einem ESS-Subnetz, **keine** `0.0.0.0`-Port-Binds,
EPICS-addr-lists/Beacon-Listen **bridge-scoped**, der Bridge bleibt `internal: true`. Das ist die #1-Sache, die bei
jedem Compose-Diff zu prüfen ist.

---

## 9. Provenance

- Read-only No-Emit-Audit (2026-06-30): 2 Multi-Agent-Workflows, kein Paket Richtung ESS — Beweise aus
  Routing/Config/offenen Sockets + Wegwerf-`egresstest-`-Test (internal-Netz hat keine Default-Route; 127.0.0.1-Publish
  vom Host = HTTP 200).
- Decision **GW** (`status/decisions.md`); Roadmap-Block „ESS-Konformität der Sandbox" (`status/roadmap.md`);
  Handover `Handover/HANDOVER-2026-06-30-essmirror-Abschluss.md` §7.
