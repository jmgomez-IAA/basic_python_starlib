#!/usr/bin/env bash
# setup_env.sh — Configura el entorno para usar la API oficial de STAR-System
# en Linux. Ejecutar con: source setup_env.sh (NO ./setup_env.sh, necesita
# "source" para que las variables export queden en tu shell actual).

# --- AJUSTA ESTAS DOS RUTAS A TU INSTALACIÓN ---
STAR_SYSTEM_ROOT="/usr/local/STAR-Dundee/STAR-System"
STAR_LIB_DIR="${STAR_SYSTEM_ROOT}/lib/x86-64"
# -------------------------------------------------

export PYTHONPATH="${STAR_SYSTEM_ROOT}/apis/python_api:${PYTHONPATH}"
export LD_LIBRARY_PATH="${STAR_LIB_DIR}:${LD_LIBRARY_PATH}"

echo "PYTHONPATH incluye:      ${STAR_SYSTEM_ROOT}/apis/python_api"
echo "LD_LIBRARY_PATH incluye: ${STAR_LIB_DIR}"

if [ ! -d "${STAR_SYSTEM_ROOT}/apis/python_api/STAR_system" ]; then
    echo "AVISO: no se encuentra STAR_system en esa ruta. Ajusta STAR_SYSTEM_ROOT en este script."
fi

if [ ! -f "${STAR_LIB_DIR}/libstar-api.so" ]; then
    echo "AVISO: no se encuentra libstar-api.so en esa ruta. Ajusta STAR_LIB_DIR en este script."
fi
