# Lokales e3-Test-IOC — echtes require/essioc, gebaut aus dem ESS-conda-Channel (anon read-only)
# via Host-CONNECT-Proxy NUR beim Build. Laufzeit: 100% offline auf 127.0.0.1 (kein ESS-Kontakt).
#
# Build:  docker build \
#   --build-arg HTTPS_PROXY=http://host.docker.internal:8899 \
#   --build-arg HTTP_PROXY=http://host.docker.internal:8899 \
#   -t epics-sandbox-e3-ioc:7.0.9 -f sandbox/ioc-e3/Dockerfile sandbox/ioc-e3
# Base-Image per Digest gepinnt (schlägt das bewegliche :latest-Tag fest). Digest auffrischen:
# docker image inspect condaforge/miniforge3:latest --format '{{index .RepoDigests 0}}' (= ein
# bewegliches Tag — beim Auffrischen den dann gültigen miniforge3-Release notieren).
FROM condaforge/miniforge3@sha256:7de9956cd783d48955835e61b8d212c26b2df901d5a5be8217bd58fb6c1bd5a4

# Proxy NUR für den conda-Install-Layer (Build-ARG). conda zieht damit die e3-Pakete aus dem
# ESS-Artifactory-conda-Channel. Landet NICHT im finalen Image-Env.
ARG HTTPS_PROXY=""
ARG HTTP_PROXY=""

# Versions-Pins (gemessen): versions-stabil, aber NICHT byte-reproduzierbar — kein conda-Lock, die
# transitiven Deps löst conda zur Build-Zeit auf. channel_alias wird NACH dem Install wieder entfernt,
# damit das weitergegebene Image keine latente ESS-Artifactory-Referenz im .condarc trägt (Laufzeit ist
# ohnehin offline). Transitive Deps (pvxs 1.5, autosave/caputlog/iocstats/recsync) zieht essioc/require automatisch.
RUN conda config --system --prepend channels ess-conda-local \
 && conda config --system --set channel_alias https://artifactory.esss.lu.se/artifactory/api/conda \
 && conda config --system --set channel_priority strict \
 && HTTPS_PROXY="$HTTPS_PROXY" HTTP_PROXY="$HTTP_PROXY" \
    conda install -n base -y epics-base=7.0.9 require=6.0.0 essioc=2.1.9 \
 && conda config --system --remove-key channel_alias \
 && conda clean -afy

WORKDIR /iocs/test-evr
COPY st.cmd fbis-dln01-evr.db fbis-dln01-evr-full.db ./

# conda run -n base aktiviert das Env (EPICS_BASE, ${essioc_DIR}, require-Pfade) und startet iocsh.
# iocsh wrappt softIocPVX -> CA (5064/5065) + PVA (5075), QSRV2. (compose published 5064/5065/5075.)
ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "base", "iocsh", "st.cmd"]
