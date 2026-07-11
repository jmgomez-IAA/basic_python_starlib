#!/usr/bin/env python3
"""
10_periodic_publish.py — Versión continua de 09_publish_mqtt.py: cada
POLL_INTERVAL_SECONDS segundos, lee RTR.LRUNSTS + RTR.PSTS de los 19 puertos
del GR718B y publica el snapshot (Line Protocol) al mismo topic MQTT.

A diferencia de 09 (lectura puntual, abre/cierra canal y conexión MQTT una
sola vez), este script mantiene el canal SpaceWire y la conexión MQTT
abiertos durante toda la ejecución, para no pagar el coste de reabrirlos en
cada ciclo.

Uso:
    python apps/10_periodic_publish.py
    (Ctrl+C para parar limpiamente)
"""

import sys
import time
import signal

DEVICE_INDEX = 1
CHANNEL_NUMBER = 1
LINK_SPEED_MBPS = 100.0

POLL_INTERVAL_SECONDS = 30.0

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


_running = True


def _handle_shutdown(signum, frame):
    global _running
    print("\nSeñal de parada recibida, terminando tras el ciclo actual...")
    _running = False


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


def capture_and_publish(channel, mqtt_client, device_serial: str, transaction_id: int) -> int:
    """
    Ejecuta un ciclo completo: lee LRUNSTS + 19x PSTS y publica el resultado.
    Devuelve el transaction_id actualizado (para seguir la secuencia entre ciclos).
    """
    lrunsts_raw, error = read_register(channel, LRUNSTS_ADDRESS, transaction_id)
    transaction_id = (transaction_id % 65535) + 1
    if lrunsts_raw is None:
        print(f"  [LRUNSTS] FALLO: {error}. Ciclo abortado.")
        return transaction_id

    running_by_port = dr.decode_lrunsts(lrunsts_raw)
    timestamp_ns = time.time_ns()

    lines = []
    errors = 0
    for port in range(1, NUM_PORTS + 1):
        address = PSTS_BASE_ADDRESS + (port - 1) * 4
        raw, error = read_register(channel, address, transaction_id)
        transaction_id = (transaction_id % 65535) + 1

        if raw is None:
            errors += 1
            continue

        status = dr.decode_psts(raw, port)
        running = running_by_port.get(port, False)
        lines.append(build_line_protocol(port, status, running, device_serial, timestamp_ns))

    if not lines:
        print("  Sin lecturas válidas, no se publica nada este ciclo.")
        return transaction_id

    payload = "\n".join(lines)
    result = mqtt_client.publish(MQTT_TOPIC, payload, qos=1)
    result.wait_for_publish(timeout=5)

    ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_ns / 1e9))
    print(f"  [{ts_str}] Publicadas {len(lines)}/{NUM_PORTS} líneas "
          f"({len(payload)} bytes){f', {errors} puerto(s) con error' if errors else ''}.")

    return transaction_id


def main():
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

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

    print(f"\nConectando a MQTT {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}...")
    try:
        mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"FALLO al conectar con el broker MQTT: {e}")
        channel.close()
        sys.exit(1)

    print(f"\nServicio iniciado. Sondeando cada {POLL_INTERVAL_SECONDS}s. Ctrl+C para parar.\n")

    transaction_id = 1
    try:
        while _running:
            cycle_start = time.time()

            transaction_id = capture_and_publish(channel, mqtt_client, device_serial, transaction_id)

            elapsed = time.time() - cycle_start
            sleep_time = max(0.0, POLL_INTERVAL_SECONDS - elapsed)
            # Dormir en trozos cortos para poder reaccionar rápido a Ctrl+C
            slept = 0.0
            while slept < sleep_time and _running:
                step = min(0.5, sleep_time - slept)
                time.sleep(step)
                slept += step
    finally:
        print("\nCerrando conexiones...")
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        channel.close()
        print("Servicio detenido.")


if __name__ == "__main__":
    main()

