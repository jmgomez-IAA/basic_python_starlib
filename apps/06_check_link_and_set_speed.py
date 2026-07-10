#!/usr/bin/env python3
"""
06_check_link_and_set_speed.py — Comprueba el estado del enlace SpaceWire del
puerto del Brick Mk3 conectado al GR718B, y reduce la velocidad de
transmisión a 10 Mbit/s (velocidad segura de arranque, útil cuando el link no
llega a conectar a la velocidad por defecto).

Uso típico: ejecutar este script ANTES de 05_read_rtr_ver.py cuando el GR718B
no detecta conexión en el puerto.

NOTA sobre LinkStatus: los nombres de atributo (triState, disable, start,
autoStart, running, linkState) se infieren de cómo se construye el objeto en
link_port.py (`LinkStatus(triState, disable, start, autoStart, running,
linkState)`), siguiendo el mismo patrón consistente que el resto de clases de
esta API (los argumentos del constructor se guardan como atributos del mismo
nombre). No he podido confirmarlo con la clase en sí (STAR_structure_classes.py),
así que si algún nombre de atributo falla, revisa ese fichero.
"""

import sys

DEVICE_INDEX = 1
CHANNEL_NUMBER = 1  # puerto físico del Brick conectado al GR718B
TARGET_SPEED_MBPS = 100.0  # float obligatorio; el board soporta hasta 200 Mbit/s

try:
    from STAR_system.STAR_system import STARSystem
    from STAR_system.link_port import LinkPort
    from STAR_system.STAR_enums import STAR_DEVICE_TYPE, STAR_CFG_SPW_LINK_STATE
    from STAR_system.STAR_exceptions import STARAPIError
except ImportError as e:
    print(f"FALLO al importar STAR_system: {e}")
    sys.exit(1)


def print_link_status(link_port: LinkPort, label: str):
    try:
        status = link_port.getSpaceWireLinkStatus()
    except STARAPIError as e:
        print(f"  [{label}] FALLO al leer el estado del link: {e}")
        return

    try:
        state_name = STAR_CFG_SPW_LINK_STATE(status.linkState).name
    except (ValueError, AttributeError):
        state_name = f"desconocido ({status.linkState})"

    print(f"  [{label}] Estado del link:")
    print(f"      running:   {status.running}")
    print(f"      linkState: {state_name}")
    print(f"      start:     {status.start}")
    print(f"      autoStart: {status.autoStart}")
    print(f"      disable:   {status.disable}")
    print(f"      triState:  {status.triState}")


def print_baudrate(link_port: LinkPort, label: str):
    try:
        rate = link_port.getTxSignallingRate()
        print(f"  [{label}] Baudrate actual (Tx): {rate} Mbit/s")
    except STARAPIError as e:
        print(f"  [{label}] FALLO al leer el baudrate: {e}")


def main():
    devices = STARSystem.getDeviceListForType(STAR_DEVICE_TYPE.STAR_DEVICE_ALL)
    if not devices:
        print("No hay dispositivos conectados.")
        sys.exit(0)
    if DEVICE_INDEX > len(devices):
        print(f"DEVICE_INDEX={DEVICE_INDEX} pero solo hay {len(devices)} dispositivo(s).")
        sys.exit(1)

    device = devices[DEVICE_INDEX - 1]
    print(f"Usando dispositivo: {device.getDeviceName()} (deviceID={device.deviceID})")
    print(f"Puerto: {CHANNEL_NUMBER}\n")

    try:
        link_port = LinkPort(device.deviceID, CHANNEL_NUMBER)
    except (TypeError, ValueError) as e:
        print(f"FALLO al crear LinkPort: {e}")
        sys.exit(1)

    print("=== Estado ANTES de tocar nada ===")
    print_link_status(link_port, "antes")
    print_baudrate(link_port, "antes")

    print(f"\nAjustando velocidad de transmisión a {TARGET_SPEED_MBPS} Mbit/s...")
    try:
        actual_rate = link_port.setTxSignallingRate(TARGET_SPEED_MBPS)
        print(f"  OK: velocidad establecida a {actual_rate} Mbit/s (el hardware puede redondear "
              f"al valor discreto más cercano soportado).")
    except (STARAPIError, TypeError, ValueError) as e:
        print(f"  FALLO al establecer la velocidad: {e}")
        sys.exit(1)

    print("\nAsegurando que el link está arrancado (startLink)...")
    try:
        link_port.startLink()
        print("  OK: startLink() llamado.")
    except STARAPIError as e:
        print(f"  FALLO en startLink(): {e}")

    import time
    time.sleep(1)  # dar tiempo al link a (re)negociar tras el cambio de velocidad

    print("\n=== Estado DESPUÉS de ajustar velocidad ===")
    print_link_status(link_port, "después")
    print_baudrate(link_port, "después")

    print("\nSi 'running' es True y 'linkState' es STAR_CFG_SPW_LINK_STATE_RUN,")
    print("el link está conectado y ya puedes probar 05_read_rtr_ver.py.")


if __name__ == "__main__":
    main()
