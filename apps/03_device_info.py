#!/usr/bin/env python3
"""
03_device_info.py — Información detallada de un dispositivo: capacidades,
canales disponibles.

Selecciona el primer dispositivo encontrado por defecto (ver DEVICE_INDEX).
"""

import sys

DEVICE_INDEX = 1  # 1 = el primero de la lista

try:
    from STAR_system.STAR_system import STARSystem
    from STAR_system.STAR_enums import STAR_DEVICE_TYPE
    from STAR_system.STAR_exceptions import STARAPIError
except ImportError as e:
    print(f"FALLO al importar STAR_system: {e}")
    sys.exit(1)

devices = STARSystem.getDeviceListForType(STAR_DEVICE_TYPE.STAR_DEVICE_ALL)
if not devices:
    print("No hay dispositivos conectados.")
    sys.exit(0)

if DEVICE_INDEX > len(devices):
    print(f"DEVICE_INDEX={DEVICE_INDEX} pero solo hay {len(devices)} dispositivo(s).")
    sys.exit(1)

device = devices[DEVICE_INDEX - 1]

print(f"Información del dispositivo #{DEVICE_INDEX}:\n")
print(f"  Nombre:        {device.getDeviceName()}")
print(f"  Nº de serie:   {device.getSerialNumber()}")
print(f"  Tipo:          {device.getDeviceType()}")
print(f"  deviceID:      {device.deviceID}")

try:
    tx_rx = device.getDeviceTxRxCapabilities()
    print(f"  Tx/Rx capable: {tx_rx}")
except STARAPIError as e:
    print(f"  Tx/Rx capable: (no disponible: {e})")

try:
    cfg_cap = device.getDeviceConfigCapabilities()
    print(f"  Config capable:{cfg_cap}")
except STARAPIError as e:
    print(f"  Config capable:(no disponible: {e})")

try:
    bus_type = device.getBusType()
    print(f"  Bus:           {bus_type}")
except STARAPIError as e:
    print(f"  Bus:           (no disponible: {e})")

print("\nCanales disponibles:")
try:
    channels = device.getChannels()
    if not channels:
        print("  (ninguno reportado)")
    for ch in channels:
        print(f"  - {ch}")
except STARAPIError as e:
    print(f"  FALLO al listar canales: {e}")
