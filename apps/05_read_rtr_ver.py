#!/usr/bin/env python3
"""
05_read_rtr_ver.py — Lectura RMAP real de un registro del GR718B, usando la
librería RMAP oficial de STAR-Dundee (rmap_packet_library.py), no una
implementación casera.

Registro leído: RTR.VER (0x00000A08), Tabla 35 del manual del GR718B:
    31:24  Major version (constante 0x01)
    23:16  Minor version (constante 0x03)
    15:8   Patch (constante 0x00)
    7:0    Instance ID (depende de pines GPIO, aún no confirmado)

Requiere: Brick Mk3 conectado por USB Y con uno de sus puertos SpaceWire
conectado físicamente a un puerto del GR718B.

SUPUESTOS A VALIDAR EMPÍRICAMENTE (documentados aquí para que quede claro
qué ajustar si la lectura falla):
  - targetAddress = [0x00, 0xFE]: el primer byte (0x00) es el que, según el
    manual del GR718B (sección 1.5), siempre enruta al puerto de
    configuración interno, independientemente de lo que venga después. El
    segundo byte (0xFE) es una Target Logical Address de convención (no
    tenemos confirmado que el puerto de configuración del GR718B la valide
    o la ignore).
  - replyAddress = [0xFE]: convención tomada del ejemplo oficial de
    STAR-Dundee. Como es un enlace directo Brick<->GR718B (sin routers
    intermedios), es razonable que no necesite un path real de vuelta.
  - key = 0: asumido sin clave de protección configurada (comportamiento
    por defecto típico).

Si la respuesta falla con RMAP_INVALID_KEY o similar, ese es el primer sitio
a revisar.
"""

import sys

DEVICE_INDEX = 1
CHANNEL_NUMBER = 1  # ajusta si tu puerto físico conectado al GR718B es otro
LINK_SPEED_MBPS = 100.0  # velocidad de operación (float obligatorio); el board soporta hasta 200 Mbit/s

RTR_VER_ADDRESS = 0x00000A08
DATA_LENGTH = 4  # registro de 32 bits

TARGET_ADDRESS = [0x00, 0xFE]
REPLY_ADDRESS = [0xFE]
KEY = 0

try:
    from STAR_system.STAR_system import STARSystem
    from STAR_system.channel import Channel
    from STAR_system.packet import Packet
    from STAR_system.link_port import LinkPort
    from STAR_system.STAR_enums import (
        STAR_DEVICE_TYPE,
        STAR_CHANNEL_DIRECTION,
        STAR_TRANSFER_STATUS,
        STAR_CFG_SPW_LINK_STATE,
    )
    from STAR_system.STAR_exceptions import STARAPIError
    from STAR_system.rmap_packet_library import (
        RMAP_BuildReadCommandPacket,
        RMAP_CheckPacketValid,
        RMAP_STATUS,
    )
except ImportError as e:
    print(f"FALLO al importar STAR_system: {e}")
    sys.exit(1)


def hexlist(data) -> str:
    return " ".join(f"{b:02X}" for b in data)


def ensure_link_ready(device, port_number: int, target_speed_mbps: float) -> bool:
    """
    Comprueba el estado del enlace SpaceWire y lo deja arrancado a
    `target_speed_mbps`. Devuelve True si el link queda en RUN, False si no.

    Ver 06_check_link_and_set_speed.py para la versión standalone comentada
    con más detalle sobre los campos de LinkStatus.
    """
    import time

    try:
        link_port = LinkPort(device.deviceID, port_number)
    except (TypeError, ValueError) as e:
        print(f"      FALLO al crear LinkPort: {e}")
        return False

    def _print_status(label):
        try:
            status = link_port.getSpaceWireLinkStatus()
            rate = link_port.getTxSignallingRate()
            try:
                state_name = STAR_CFG_SPW_LINK_STATE(status.linkState).name
            except (ValueError, AttributeError):
                state_name = f"desconocido ({status.linkState})"
            print(f"      [{label}] running={status.running} linkState={state_name} rate={rate} Mbit/s")
            return status, rate
        except STARAPIError as e:
            print(f"      [{label}] FALLO al leer estado del link: {e}")
            return None, None

    status, rate = _print_status("actual")

    already_ready = (
        status is not None
        and status.running
        and status.linkState == STAR_CFG_SPW_LINK_STATE.STAR_CFG_SPW_LINK_STATE_RUN
        and rate == target_speed_mbps
    )
    if already_ready:
        print("      El link ya estaba listo, no hace falta tocar nada.")
        return True

    print(f"      Ajustando velocidad a {target_speed_mbps} Mbit/s y arrancando el link...")
    try:
        link_port.setTxSignallingRate(target_speed_mbps)
        link_port.startLink()
    except STARAPIError as e:
        print(f"      FALLO al configurar el link: {e}")
        return False

    time.sleep(1)  # dar tiempo a renegociar

    status, _ = _print_status("tras ajuste")
    if status is None:
        return False

    return status.running and status.linkState == STAR_CFG_SPW_LINK_STATE.STAR_CFG_SPW_LINK_STATE_RUN


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

    # --- 0. Asegurar que el enlace SpaceWire está arrancado a la velocidad deseada ---
    print(f"\n[0/5] Comprobando/preparando enlace en puerto {CHANNEL_NUMBER}...")
    link_ready = ensure_link_ready(device, CHANNEL_NUMBER, LINK_SPEED_MBPS)
    if not link_ready:
        print("      FALLO: el link no ha quedado en RUN. Abortando antes de enviar nada.")
        sys.exit(1)
    print("      OK: link en RUN.")

    # --- 1. Construir el comando RMAP de lectura ---
    transaction_id = 1
    print(f"\n[1/5] Construyendo comando RMAP de lectura hacia 0x{RTR_VER_ADDRESS:08X}...")
    try:
        command_bytes, command_struct = RMAP_BuildReadCommandPacket(
            targetAddress=TARGET_ADDRESS,
            replyAddress=REPLY_ADDRESS,
            incrementAddress=False,
            key=KEY,
            transactionIdentifier=transaction_id,
            readAddress=RTR_VER_ADDRESS,
            extendedReadAddress=0,
            dataLength=DATA_LENGTH,
            alignment=1,
        )
    except (STARAPIError, TypeError, ValueError) as e:
        print(f"      FALLO al construir el comando: {e}")
        sys.exit(1)
    print(f"      OK: {len(command_bytes)} bytes -> {hexlist(command_bytes)}")

    # --- 2. Abrir el canal ---
    print(f"\n[2/5] Abriendo canal {CHANNEL_NUMBER}...")
    try:
        channel = Channel(CHANNEL_NUMBER, device.deviceID)
        channel.openChannelToDevice(STAR_CHANNEL_DIRECTION.INOUT)
    except STARAPIError as e:
        print(f"      FALLO al abrir el canal: {e}")
        sys.exit(1)
    print("      OK: canal abierto.")

    try:
        # --- 3. Transmitir el comando ---
        print("\n[3/5] Transmitiendo comando RMAP...")
        packet = Packet(command_bytes)
        try:
            channel.transmitPacket(packet, timeout=1000)
        except STARAPIError as e:
            print(f"      FALLO al transmitir: {e}")
            sys.exit(1)
        print("      OK: comando transmitido.")

        # --- 4. Recibir la respuesta ---
        print("\n[4/5] Esperando respuesta...")
        try:
            status, reply_packet = channel.receivePacket(bufferLength=64, timeout=1000)
        except STARAPIError as e:
            print(f"      FALLO al recibir: {e}")
            sys.exit(1)

        if status != STAR_TRANSFER_STATUS.STAR_TRANSFER_STATUS_COMPLETE or reply_packet is None:
            print(f"      Sin respuesta (status={status}). Posibles causas:")
            print("      - El puerto conectado al GR718B no es el CHANNEL_NUMBER correcto.")
            print("      - El GR718B no está realmente alimentado/enlazado (revisa el LED de link).")
            print("      - targetAddress/key no coinciden con lo que el GR718B espera.")
            sys.exit(1)

        raw_reply = reply_packet.getPacketData()
        print(f"      OK: respuesta recibida, {len(raw_reply)} bytes -> {hexlist(raw_reply)}")

        # --- Parsear la respuesta con la librería RMAP oficial ---
        rmap_status, reply_struct = RMAP_CheckPacketValid(raw_reply, True)
        if rmap_status != RMAP_STATUS.RMAP_SUCCESS:
            print(f"\nFALLO: paquete RMAP inválido o con error: {rmap_status}")
            sys.exit(1)

        if reply_struct.transactionIdentifier != transaction_id:
            print(
                f"\nAVISO: transactionIdentifier no coincide "
                f"(esperado {transaction_id}, recibido {reply_struct.transactionIdentifier})"
            )

        data = reply_struct.data
        print(f"\nDatos de RTR.VER: {hexlist(data)}")

        if len(data) == 4:
            major, minor, patch, instance_id = data
            print(f"  Major version:  0x{major:02X}")
            print(f"  Minor version:  0x{minor:02X}")
            print(f"  Patch:          0x{patch:02X}")
            print(f"  Instance ID:    0x{instance_id:02X}")
        else:
            print(f"  (se esperaban 4 bytes, se recibieron {len(data)})")

    finally:
        channel.close()
        print("\nCanal cerrado.")


if __name__ == "__main__":
    main()
