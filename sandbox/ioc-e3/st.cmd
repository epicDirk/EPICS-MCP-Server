# e3 st.cmd — lokales Test-IOC FBIS-DLN01:Ctrl-EVR-01 (Event Receiver, Soft/Sim).
# iocsh (e3) wrappt softIocPVX -> serviert die Records über CA UND PVA (QSRV2).
# iocInit wird von iocsh automatisch angehängt (NICHT hier aufrufen).
#
# v2: volles essioc via common_config.iocsh (autosave/caputlog/iocStats/recsync/access-security).
# Lokales Test-IOC -> Log-/CaPutLog-Server laufen nicht (localhost) -> iocLog/caPutLog können sich
# nicht verbinden (nicht-fatal, iocInit läuft weiter). recsync/reccaster meldet die Records an einen
# recceiver an (Phase B, container-to-container). autosave braucht ein beschreibbares AS_TOP.

require essioc

# essioc/common_config-Pflicht-Env (vor dem iocshLoad):
epicsEnvSet("IOCNAME", "FBIS-DLN01-Ctrl-EVR-01")
epicsEnvSet("IOCDIR",  "FBIS-DLN01-Ctrl-EVR-01")
epicsEnvSet("AS_TOP",  "/iocs/test-evr/autosave")
epicsEnvSet("ERRORLOG_SERVER_PORT", "7004")
epicsEnvSet("CAPUTLOG_SERVER_PORT", "7011")

iocshLoad("$(essioc_DIR)/common_config.iocsh")

epicsEnvSet("P", "FBIS-DLN01:Ctrl-EVR-01:")
dbLoadRecords("fbis-dln01-evr.db", "P=$(P)")
