#!/usr/bin/env python3
"""
01_api_version.py — Prueba más básica posible: ¿carga la librería STAR-API y
podemos leer su versión?

No requiere ningún dispositivo conectado.
"""

import sys

try:
    from STAR_system.STAR_system import STARSystem
    from STAR_system.STAR_exceptions import STARAPIError
except ImportError as e:
    print(f"FALLO al importar STAR_system: {e}")
    print("Comprueba que has hecho 'source setup_env.sh' antes de ejecutar este script,")
    print("y que tienes instalados: pip install numpy psutil dill")
    sys.exit(1)

print("Consultando versión de STAR-API...")
try:
    version = STARSystem.getApiVersion()
    print(f"  Nombre:  {version.name}")
    print(f"  Autor:   {version.author}")
    print(f"  Versión: {version.major}.{version.minor}.{version.edit}.{version.patch}")
    print("\nOK — la librería carga y responde correctamente.")
except STARAPIError as e:
    print(f"FALLO: {e}")
    print("Comprueba: ¿LD_LIBRARY_PATH apunta a la carpeta con libstar-api.so?")
    sys.exit(1)
