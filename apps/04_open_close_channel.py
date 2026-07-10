#!/usr/bin/env python3
"""
04_open_close_channel.py — Abre y cierra un canal de un dispositivo, para
validar que la comunicación básica funciona (sin enviar/recibir paquetes
todavía, eso vendrá en un mini-proyecto posterior de envío/recepción).
"""

import sys

DEVICE_INDEX = 1
CHANNEL_NUMBER = 1  # el Brick Mk3 tiene 2 puertos SpaceWire, prueba 1 o 2

try:
    from STAR_system.STAR_system import STARSystem
    from STAR_system.channel import Channel
    from STAR_system.STAR_enums import STAR_DEVICE_TYPE, STAR_CHANNEL_DIRECTION
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
print(f"Usando dispositivo: {device.getDeviceName()} (deviceID={device.deviceID})")

print(f"\nAbriendo canal {CHANNEL_NUMBER} en modo INOUT...")
try:
    channel = Channel(CHANNEL_NUMBER, device.deviceID)
    channel.openChannelToDevice(STAR_CHANNEL_DIRECTION.INOUT)
    print(f"  OK: canal abierto. isOpen() = {channel.isOpen()}")
except STARAPIError as e:
    print(f"  FALLO al abrir el canal: {e}")
    print("  Comprueba: ¿el número de canal es válido? ¿otro proceso lo tiene abierto")
    print("  (p.ej. una app gráfica de STAR-System)?")
    sys.exit(1)

print("\nCerrando canal...")
try:
    channel.close()
    print(f"  OK: canal cerrado. isOpen() = {channel.isOpen()}")
except STARAPIError as e:
    print(f"  FALLO al cerrar el canal: {e}")
    sys.exit(1)

print("\nTodo OK — apertura/cierre de canal validado.")
