#!/usr/bin/env python3
"""
09_publish_mqtt.py — Lectura puntual (una sola vez) de RTR.LRUNSTS y
RTR.PSTS de todos los puertos del GR718B, decodificados y publicados a un
broker MQTT (Mosquitto) en formato InfluxDB Line Protocol — pensado para ser
consumido por Telegraf (plugin mqtt_consumer, data_format="influx") y de ahí
a InfluxDB.

Flujo: GR718B --RMAP--> este script --MQTT (Line Protocol)--> Mosquitto
       --Telegraf--> InfluxDB --> [agente ML/IA]

A diferencia de 07_dump_memory.py (que vuelca TODO el espacio de
direcciones), este script solo lee los registros relevantes para
monitorización (19 lecturas de RTR.PSTS + 1 de RTR.LRUNSTS = 20
transacciones RMAP), mucho más ligero para un sondeo periódico futuro.

Formato de cada línea publicada (una por puerto):
    gr718b_port,port=<N>,port_type=<spacewire|sist>,device=<serial> \
        running=<0|1>i,link_state="<estado>",parity_error=<0|1>i, \
        disconnect_error=<0|1>i,escape_error=<0|1>i,credit_error=<0|1>i, \
        invalid_address=<0|1>i,tx_fifo_full=<0|1>i,rx_fifo_empty=<0|1>i \
        <timestamp_ns>

Requiere: pip install paho-mqtt (además de numpy/psutil/dill de la API oficial)
"""

import sys
import time

DEVICE_INDEX = 1
CHANNEL_NUMBER = 1
LINK_SPEED_MBPS = 100.0

LRUNSTS_ADDRESS = 0x00000A40
PSTS_BASE_ADDRESS = 0x00000884
NUM_PORTS = 19  # 1-18 SpaceWire, 19 = SIST

TARGET_ADDRESS = [0x00, 0xFE]
REPLY_ADDRESS = [0xFE]
KEY = 0

MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 1883
MQTT_TOPIC = "spacewire/gr718b/metrics"

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
    import decode_registers as dr
except ImportError as e:
    print(f"FALLO al importar dependencias de STAR_system: {e}")
    sys.exit(1)

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("FALLO: falta paho-mqtt. Instala con: pip install paho-mqtt")
    sys.exit(1)


def ensure_link_ready(device, port_number: int, target_speed_mbps: float) -> bool:
    """Ver 06_check_link_and_set_speed.py para la versión comentada en detalle."""
    try:
        link_port = LinkPort(device.deviceID, port_number)
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
        return True

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

    return status.running and status.linkState == STAR_CFG_SPW_LINK_STATE.STAR_CFG_SPW_LINK_STATE_RUN


def read_register(channel, address: int, transaction_id: int):
    """Lee un registro de 4 bytes vía RMAP. Devuelve (valor_u32 | None, error | None)."""
    try:
        command_bytes, _ = RMAP_BuildReadCommandPacket(
            targetAddress=TARGET_ADDRESS,
            replyAddress=REPLY_ADDRESS,
            incrementAddress=True,
            key=KEY,
            transactionIdentifier=transaction_id,
            readAddress=address,
            extendedReadAddress=0,
            dataLength=4,
            alignment=1,
        )
    except (STARAPIError, TypeError, ValueError) as e:
        return None, f"error construyendo comando: {e}"

    try:
        channel.transmitPacket(Packet(command_bytes), timeout=1000)
        status, reply_packet = channel.receivePacket(bufferLength=64, timeout=1000)
    except STARAPIError as e:
        return None, f"error transmitiendo/recibiendo: {e}"

    if status != STAR_TRANSFER_STATUS.STAR_TRANSFER_STATUS_COMPLETE or reply_packet is None:
        return None, f"sin respuesta (status={status})"

    raw_reply = reply_packet.getPacketData()
    rmap_status, reply_struct = RMAP_CheckPacketValid(raw_reply, True)
    if rmap_status != RMAP_STATUS.RMAP_SUCCESS:
        return None, f"paquete RMAP inválido: {rmap_status}"

    if reply_struct.transactionIdentifier != transaction_id or len(reply_struct.data) != 4:
        return None, "respuesta inconsistente"

    return int.from_bytes(bytes(reply_struct.data), byteorder="big"), None


def build_line_protocol(port: int, status: "dr.PortStatus", running: bool,
                         device_serial: str, timestamp_ns: int) -> str:
    port_type = "sist" if status.port_type == "SIST" else "spacewire"
    link_state = status.link_state or "n/a"

    fields = [
        f"running={int(running)}i",
        f'link_state="{link_state}"',
        f"parity_error={int(bool(status.parity_error))}i",
        f"disconnect_error={int(bool(status.disconnect_error))}i",
        f"escape_error={int(bool(status.escape_error))}i",
        f"credit_error={int(bool(status.credit_error))}i",
        f"invalid_address={int(status.invalid_address_error)}i",
        f"tx_fifo_full={int(status.transmit_fifo_full)}i",
        f"rx_fifo_empty={int(status.receive_fifo_empty)}i",
    ]

    return (
        f"gr718b_port,port={port},port_type={port_type},device={device_serial} "
        + ",".join(fields)
        + f" {timestamp_ns}"
    )


def main():
    devices = STARSystem.getDeviceListForType(STAR_DEVICE_TYPE.STAR_DEVICE_ALL)
    if not devices:
        print("No hay dispositivos conectados.")
        sys.exit(0)
    if DEVICE_INDEX > len(devices):
        print(f"DEVICE_INDEX={DEVICE_INDEX} pero solo hay {len(devices)} dispositivo(s).")
        sys.exit(1)

    device = devices[DEVICE_INDEX - 1]
    device_serial = device.getSerialNumber()
    print(f"Usando dispositivo: {device.getDeviceName()} (deviceID={device.deviceID})")

    print(f"\nComprobando/preparando enlace en puerto {CHANNEL_NUMBER}...")
    if not ensure_link_ready(device, CHANNEL_NUMBER, LINK_SPEED_MBPS):
        print("FALLO: el link no ha quedado en RUN. Abortando.")
        sys.exit(1)
    print("      OK: link en RUN.")

    try:
        channel = Channel(CHANNEL_NUMBER, device.deviceID)
        channel.openChannelToDevice(STAR_CHANNEL_DIRECTION.INOUT)
    except STARAPIError as e:
        print(f"FALLO al abrir el canal: {e}")
        sys.exit(1)

    transaction_id = 1
    lines = []
    read_errors = []

    try:
        # --- RTR.LRUNSTS (1 lectura, cubre todos los puertos) ---
        print("\nLeyendo RTR.LRUNSTS...")
        lrunsts_raw, error = read_register(channel, LRUNSTS_ADDRESS, transaction_id)
        transaction_id = (transaction_id % 65535) + 1
        if lrunsts_raw is None:
            print(f"  FALLO: {error}. Abortando (no se puede saber qué puertos están en RUN).")
            sys.exit(1)
        running_by_port = dr.decode_lrunsts(lrunsts_raw)
        print(f"  OK: 0x{lrunsts_raw:08X}")

        # --- RTR.PSTS por puerto (19 lecturas) ---
        timestamp_ns = time.time_ns()
        print(f"\nLeyendo RTR.PSTS de {NUM_PORTS} puertos...")
        for port in range(1, NUM_PORTS + 1):
            address = PSTS_BASE_ADDRESS + (port - 1) * 4
            raw, error = read_register(channel, address, transaction_id)
            transaction_id = (transaction_id % 65535) + 1

            if raw is None:
                print(f"  Puerto {port}: FALLO ({error})")
                read_errors.append((port, error))
                continue

            status = dr.decode_psts(raw, port)
            running = running_by_port.get(port, False)
            line = build_line_protocol(port, status, running, device_serial, timestamp_ns)
            lines.append(line)
            print(f"  Puerto {port}: OK")

    finally:
        channel.close()

    if not lines:
        print("\nNo se ha podido leer ningún puerto correctamente. No se publica nada.")
        sys.exit(1)

    print(f"\n{len(lines)}/{NUM_PORTS} líneas Line Protocol construidas"
          f"{f', {len(read_errors)} puerto(s) con error' if read_errors else ''}.")

    # --- Publicar a MQTT ---
    print(f"\nConectando a MQTT {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}...")
    try:
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT)
        client.loop_start()
    except Exception as e:
        print(f"FALLO al conectar con el broker MQTT: {e}")
        sys.exit(1)

    payload = "\n".join(lines)  # Telegraf/InfluxDB aceptan varias líneas separadas por \n
    result = client.publish(MQTT_TOPIC, payload, qos=1)
    result.wait_for_publish(timeout=5)

    client.loop_stop()
    client.disconnect()

    print(f"Publicado en topic '{MQTT_TOPIC}' ({len(payload)} bytes, {len(lines)} líneas).")
    print("\nEjemplo de línea publicada:")
    print(f"  {lines[0]}")


if __name__ == "__main__":
    main()

