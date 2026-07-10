#!/usr/bin/env python3
"""
07_dump_memory.py — Volcado completo del espacio de direcciones RMAP del
GR718B (0x00000000 - 0x00002FFC: router, tabla de rutado, SPI, GPIO y
reservado), usando la librería RMAP oficial de STAR-Dundee.

Restricciones del puerto de configuración del GR718B respetadas aquí
(confirmadas en el manual, sección sobre el target RMAP del puerto de
configuración):
  - Target Logical Address = 0xFE          -> TARGET_ADDRESS = [0x00, 0xFE]
  - Address 4-byte alineada                -> iteramos en pasos de 4/128
  - Extended Address = 0x00                -> extendedReadAddress=0
  - Key = 0x00                             -> KEY = 0
  - Data Length múltiplo de 4, 0-128 B     -> CHUNK_SIZE = 128 (32 registros)

Nota sobre Reply Address: el manual confirma que el puerto de configuración
usa "implicit partial return address" — la respuesta siempre vuelve por el
mismo puerto físico por el que llegó el comando, sin importar el valor del
campo Reply Address. Por eso REPLY_ADDRESS=[0xFE] (heredado de 05) funciona
sin problema.

Salida:
  - gr718b_dump.bin: volcado binario crudo (12288 bytes)
  - gr718b_dump.txt: volcado en hexadecimal, anotado con nombres de
    registro conocidos (ver register_map.py)
"""

import sys
import time

DEVICE_INDEX = 1
CHANNEL_NUMBER = 1
LINK_SPEED_MBPS = 10.0

DUMP_START_ADDRESS = 0x00000000
DUMP_END_ADDRESS = 0x00002FFC  # inclusive, último registro válido documentado
CHUNK_SIZE = 128  # bytes, máximo permitido por el target del GR718B

TARGET_ADDRESS = [0x00, 0xFE]
REPLY_ADDRESS = [0xFE]
KEY = 0

MAX_RETRIES_PER_CHUNK = 2

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
    import register_map
except ImportError as e:
    print(f"FALLO al importar dependencias: {e}")
    sys.exit(1)


def ensure_link_ready(device, port_number: int, target_speed_mbps: float) -> bool:
    """Ver 06_check_link_and_set_speed.py para la versión comentada en detalle."""
    try:
        link_port = LinkPort(device.deviceID, port_number)
    except (TypeError, ValueError) as e:
        print(f"      FALLO al crear LinkPort: {e}")
        return False

    try:
        status = link_port.getSpaceWireLinkStatus()
        rate = link_port.getTxSignallingRate()
    except STARAPIError as e:
        print(f"      FALLO al leer estado del link: {e}")
        return False

    already_ready = (
        status.running
        and status.linkState == STAR_CFG_SPW_LINK_STATE.STAR_CFG_SPW_LINK_STATE_RUN
        and rate == target_speed_mbps
    )
    if already_ready:
        print(f"      Link ya listo (running=True, RUN, {rate} Mbit/s).")
        return True

    print(f"      Ajustando velocidad a {target_speed_mbps} Mbit/s y arrancando el link...")
    try:
        link_port.setTxSignallingRate(target_speed_mbps)
        link_port.startLink()
    except STARAPIError as e:
        print(f"      FALLO al configurar el link: {e}")
        return False

    time.sleep(1)

    try:
        status = link_port.getSpaceWireLinkStatus()
    except STARAPIError as e:
        print(f"      FALLO al releer estado del link: {e}")
        return False

    ok = status.running and status.linkState == STAR_CFG_SPW_LINK_STATE.STAR_CFG_SPW_LINK_STATE_RUN
    print(f"      Estado tras ajuste: running={status.running}, "
          f"linkState={STAR_CFG_SPW_LINK_STATE(status.linkState).name}")
    return ok


def read_chunk(channel, address: int, length: int, transaction_id: int):
    """
    Lee `length` bytes (múltiplo de 4, máx 128) desde `address` vía RMAP.
    Devuelve (bytes_leidos | None, mensaje_error | None).
    """
    try:
        command_bytes, _ = RMAP_BuildReadCommandPacket(
            targetAddress=TARGET_ADDRESS,
            replyAddress=REPLY_ADDRESS,
            incrementAddress=True,
            key=KEY,
            transactionIdentifier=transaction_id,
            readAddress=address,
            extendedReadAddress=0,
            dataLength=length,
            alignment=1,
        )
    except (STARAPIError, TypeError, ValueError) as e:
        return None, f"error construyendo comando: {e}"

    try:
        packet = Packet(command_bytes)
        channel.transmitPacket(packet, timeout=1000)
    except STARAPIError as e:
        return None, f"error transmitiendo: {e}"

    try:
        status, reply_packet = channel.receivePacket(bufferLength=256, timeout=1000)
    except STARAPIError as e:
        return None, f"error recibiendo: {e}"

    if status != STAR_TRANSFER_STATUS.STAR_TRANSFER_STATUS_COMPLETE or reply_packet is None:
        return None, f"sin respuesta (status={status})"

    raw_reply = reply_packet.getPacketData()
    rmap_status, reply_struct = RMAP_CheckPacketValid(raw_reply, True)
    if rmap_status != RMAP_STATUS.RMAP_SUCCESS:
        return None, f"paquete RMAP inválido: {rmap_status}"

    if reply_struct.transactionIdentifier != transaction_id:
        return None, (
            f"transactionIdentifier no coincide "
            f"(esperado {transaction_id}, recibido {reply_struct.transactionIdentifier})"
        )

    if len(reply_struct.data) != length:
        return None, f"longitud inesperada (esperados {length}, recibidos {len(reply_struct.data)})"

    return bytes(reply_struct.data), None


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

    print(f"\nComprobando/preparando enlace en puerto {CHANNEL_NUMBER}...")
    if not ensure_link_ready(device, CHANNEL_NUMBER, LINK_SPEED_MBPS):
        print("FALLO: el link no ha quedado en RUN. Abortando.")
        sys.exit(1)

    total_bytes = DUMP_END_ADDRESS - DUMP_START_ADDRESS + 4  # +4: DUMP_END_ADDRESS es la última palabra, inclusive
    num_chunks = total_bytes // CHUNK_SIZE
    print(f"\nVolcando {total_bytes} bytes (0x{DUMP_START_ADDRESS:08X} - 0x{DUMP_END_ADDRESS + 3:08X}) "
          f"en {num_chunks} peticiones de {CHUNK_SIZE} bytes cada una.\n")

    try:
        channel = Channel(CHANNEL_NUMBER, device.deviceID)
        channel.openChannelToDevice(STAR_CHANNEL_DIRECTION.INOUT)
    except STARAPIError as e:
        print(f"FALLO al abrir el canal: {e}")
        sys.exit(1)

    dump = bytearray()
    failed_chunks = []
    transaction_id = 1

    try:
        for i in range(num_chunks):
            address = DUMP_START_ADDRESS + i * CHUNK_SIZE

            data = None
            error = None
            for attempt in range(MAX_RETRIES_PER_CHUNK + 1):
                data, error = read_chunk(channel, address, CHUNK_SIZE, transaction_id)
                transaction_id = (transaction_id % 65535) + 1
                if data is not None:
                    break

            if data is None:
                print(f"  [{i + 1}/{num_chunks}] 0x{address:08X}  FALLO tras "
                      f"{MAX_RETRIES_PER_CHUNK + 1} intentos: {error}")
                failed_chunks.append((address, error))
                dump.extend(b"\xff" * CHUNK_SIZE)  # relleno para no desalinear el volcado
            else:
                print(f"  [{i + 1}/{num_chunks}] 0x{address:08X}  OK ({CHUNK_SIZE} bytes)")
                dump.extend(data)

    finally:
        channel.close()

    print(f"\nVolcado completo: {len(dump)} bytes, {len(failed_chunks)} bloque(s) fallido(s).")
    if failed_chunks:
        print("Bloques fallidos (rellenados con 0xFF en el volcado):")
        for address, error in failed_chunks:
            print(f"  0x{address:08X}: {error}")

    # --- Guardar volcado binario ---
    with open("gr718b_dump.bin", "wb") as f:
        f.write(dump)
    print("\nGuardado: gr718b_dump.bin")

    # --- Guardar volcado en hexadecimal anotado ---
    with open("gr718b_dump.txt", "w") as f:
        for offset in range(0, len(dump), 4):
            address = DUMP_START_ADDRESS + offset
            word = dump[offset:offset + 4]
            hex_str = " ".join(f"{b:02X}" for b in word)
            label = register_map.name_for_address(address)
            line = f"0x{address:08X}: {hex_str}"
            if label:
                line += f"   ; {label}"
            f.write(line + "\n")
    print("Guardado: gr718b_dump.txt (anotado con nombres de registro conocidos)")


if __name__ == "__main__":
    main()
