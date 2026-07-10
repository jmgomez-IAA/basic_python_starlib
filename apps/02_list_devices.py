#!/usr/bin/env python3
"""
02_list_devices.py — Lista todos los dispositivos STAR-Dundee conectados
(Brick Mk3, routers, etc.).

Requiere que la librería cargue correctamente (ver 01_api_version.py primero
si esto falla en un paso inesperado).
"""

import sys

try:
    from STAR_system.STAR_system import STARSystem
    from STAR_system.STAR_enums import STAR_DEVICE_TYPE
    from STAR_system.STAR_exceptions import STARAPIError
except ImportError as e:
    print(f"FALLO al importar STAR_system: {e}")
    sys.exit(1)

print("Buscando dispositivos STAR-Dundee conectados...")
try:
    devices = STARSystem.getDeviceListForType(STAR_DEVICE_TYPE.STAR_DEVICE_ALL)
except STARAPIError as e:
    print(f"FALLO: {e}")
    sys.exit(1)

if not devices:
    print("No se ha encontrado ningún dispositivo.")
    print("¿Está el Brick Mk3 (o el dispositivo que sea) conectado por USB?")
    sys.exit(0)

print(f"\n{len(devices)} dispositivo(s) encontrado(s):\n")
for i, dev in enumerate(devices, start=1):
    try:
        name = dev.getDeviceName()
    except STARAPIError:
        name = "(nombre no disponible)"
    try:
        serial = dev.getSerialNumber()
    except STARAPIError:
        serial = "?"
    try:
        dev_type = dev.getDeviceType()
    except STARAPIError:
        dev_type = "?"

    print(f"  [{i}] {name}")
    print(f"      Tipo:          {dev_type}")
    print(f"      Nº de serie:   {serial}")
    print(f"      deviceID:      {dev.deviceID}")
    print()
