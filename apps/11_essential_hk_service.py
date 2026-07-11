#!/usr/bin/env python3
"""
11_essential_hk_service.py — Servicio de housekeeping "Esencial" del GR718B,
cada POLL_INTERVAL_SECONDS (10s por defecto).

Programa INDEPENDIENTE de 09_publish_mqtt.py / 10_periodic_publish.py (no los
importa ni los extiende) — comparte únicamente los módulos de soporte
decode_registers.py y register_map.py.

Diferencia clave respecto a 10_periodic_publish.py: en vez de 20 lecturas
RMAP individuales (1 registro/transacción), agrupa las lecturas en 6
transacciones fijas aprovechando que varios bloques de registros son
contiguos en el espacio de direcciones del GR718B. Tabla de comandos:

  Cmd 1: RTR.LRUNSTS              0x00000A40   4 B   (bitmap de enlace)
  Cmd 2: RTR.PSTS  (puertos 1-19) 0x00000884  76 B   (19 x 4B, contiguo)
  Cmd 3: Contadores (puertos 1-8)   0x00000C10 128 B  (8 x 16B, contiguo)
  Cmd 4: Contadores (puertos 9-16)  0x00000C90 128 B  (8 x 16B, contiguo)
  Cmd 5: Contadores (puertos 17-19) 0x00000D10  48 B  (3 x 16B, contiguo)
  Cmd 6: RTR.CREDCNT (puertos 1-18) 0x00000E84  72 B  (18 x 4B, contiguo)

Cada bloque de contadores tiene 4 registros de 4B por puerto, en este orden
fijo dentro de los 16B: OCHARCNT, ICHARCNT, OPKTCNT, IPKTCNT.

Añade al mismo measurement/topic que 09/10 (gr718b_port) los campos nuevos
de tráfico y crédito — InfluxDB no requiere que todos los puntos tengan el
mismo conjunto de campos, así que conviven sin problema con los puntos más
ligeros que publique el servicio Mínimo si corre en paralelo.
"""

import sys
import time
import signal
import struct

DEVICE_INDEX = 1
CHANNEL_NUMBER = 1
LINK_SPEED_MBPS = 100.0

POLL_INTERVAL_SECONDS = 10.0

TARGET_ADDRESS = [0x00, 0xFE]
REPLY_ADDRESS = [0xFE]
KEY = 0

MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 1883
MQTT_TOPIC = "spacewire/gr718b/metrics"

# --- Tabla de comandos RMAP del nivel Esencial (verificada contra el manual) ---
LRUNSTS_ADDRESS = 0x00000A40

PSTS_BASE = 0x00000884
PSTS_LENGTH = 76  # 19 puertos x 4B

COUNTERS_CHUNKS = [
    # (dirección base, longitud, puerto_inicial, num_puertos)
    (0x00000C10, 128, 1, 8),
    (0x00000C90, 128, 9, 8),
    (0x00000D10, 48, 17, 3),
]

CREDCNT_BASE = 0x00000E84
CREDCNT_LENGTH = 72  # 18 puertos x 4B

NUM_PORTS = 19

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
    """Programa independiente: esta función se duplica intencionadamente
    respecto a la de 06/09/10, no se importa de ningún otro script."""
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


def read_block(channel, address: int, length: int, transaction_id: int):
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
        channel.transmitPacket(Packet(command_bytes), timeout=1000)
        status, reply_packet = channel.receivePacket(bufferLength=256, timeout=1000)
    except STARAPIError as e:
        return None, f"error transmitiendo/recibiendo: {e}"

    if status != STAR_TRANSFER_STATUS.STAR_TRANSFER_STATUS_COMPLETE or reply_packet is None:
        return None, f"sin respuesta (status={status})"

    raw_reply = reply_packet.getPacketData()
    rmap_status, reply_struct = RMAP_CheckPacketValid(raw_reply, True)
    if rmap_status != RMAP_STATUS.RMAP_SUCCESS:
        return None, f"paquete RMAP inválido: {rmap_status}"

    if reply_struct.transactionIdentifier != transaction_id or len(reply_struct.data) != length:
        return None, "respuesta inconsistente"

    return bytes(reply_struct.data), None


def parse_u32_be(data: bytes, offset: int) -> int:
    return struct.unpack(">I", data[offset:offset + 4])[0]


def build_line_protocol(port: int, status: "dr.PortStatus", running: bool,
                         counters: dict, credit: "int | None",
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
        f"outgoing_chars={counters['ochar']}i",
        f"incoming_chars={counters['ichar']}i",
        f"outgoing_packets={counters['opkt']}i",
        f"incoming_packets={counters['ipkt']}i",
    ]
    if credit is not None:
        fields.append(f"credit_count={credit}i")

    return (
        f"gr718b_port,port={port},port_type={port_type},device={device_serial} "
        + ",".join(fields)
        + f" {timestamp_ns}"
    )


def capture_essential_cycle(channel, mqtt_client, device_serial: str, transaction_id: int) -> int:
    """Ejecuta las 6 transacciones RMAP del nivel Esencial y publica el resultado."""

    # --- Cmd 1: RTR.LRUNSTS ---
    data, error = read_block(channel, LRUNSTS_ADDRESS, 4, transaction_id)
    transaction_id = (transaction_id % 65535) + 1
    if data is None:
        print(f"  [Cmd1/LRUNSTS] FALLO: {error}. Ciclo abortado.")
        return transaction_id
    lrunsts_raw = parse_u32_be(data, 0)
    running_by_port = dr.decode_lrunsts(lrunsts_raw)

    # --- Cmd 2: RTR.PSTS (19 puertos de golpe) ---
    data, error = read_block(channel, PSTS_BASE, PSTS_LENGTH, transaction_id)
    transaction_id = (transaction_id % 65535) + 1
    if data is None:
        print(f"  [Cmd2/PSTS] FALLO: {error}. Ciclo abortado.")
        return transaction_id
    psts_by_port = {}
    for port in range(1, NUM_PORTS + 1):
        raw = parse_u32_be(data, (port - 1) * 4)
        psts_by_port[port] = dr.decode_psts(raw, port)

    # --- Cmd 3-5: Contadores de tráfico, en 3 chunks ---
    counters_by_port = {}
    for base_addr, length, first_port, num_ports in COUNTERS_CHUNKS:
        data, error = read_block(channel, base_addr, length, transaction_id)
        transaction_id = (transaction_id % 65535) + 1
        if data is None:
            print(f"  [Cmd Contadores @0x{base_addr:08X}] FALLO: {error}. "
                  f"Puertos {first_port}-{first_port + num_ports - 1} sin datos este ciclo.")
            continue
        for i in range(num_ports):
            port = first_port + i
            offset = i * 16
            counters_by_port[port] = {
                "ochar": parse_u32_be(data, offset + 0),
                "ichar": parse_u32_be(data, offset + 4),
                "opkt": parse_u32_be(data, offset + 8),
                "ipkt": parse_u32_be(data, offset + 12),
            }

    # --- Cmd 6: RTR.CREDCNT (18 puertos de golpe) ---
    data, error = read_block(channel, CREDCNT_BASE, CREDCNT_LENGTH, transaction_id)
    transaction_id = (transaction_id % 65535) + 1
    credit_by_port = {}
    if data is None:
        print(f"  [Cmd6/CREDCNT] FALLO: {error}. Sin datos de crédito este ciclo.")
    else:
        for port in range(1, 19):  # 1-18, no incluye el puerto SIST
            credit_by_port[port] = parse_u32_be(data, (port - 1) * 4)

    # --- Construir y publicar ---
    timestamp_ns = time.time_ns()
    lines = []
    for port in range(1, NUM_PORTS + 1):
        if port not in psts_by_port or port not in counters_by_port:
            continue  # puerto sin datos completos este ciclo, se omite
        status = psts_by_port[port]
        running = running_by_port.get(port, False)
        counters = counters_by_port[port]
        credit = credit_by_port.get(port)  # None para el puerto 19 (SIST)
        lines.append(build_line_protocol(port, status, running, counters, credit,
                                          device_serial, timestamp_ns))

    if not lines:
        print("  Sin lecturas completas, no se publica nada este ciclo.")
        return transaction_id

    payload = "\n".join(lines)
    result = mqtt_client.publish(MQTT_TOPIC, payload, qos=1)
    result.wait_for_publish(timeout=5)

    ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_ns / 1e9))
    print(f"  [{ts_str}] Publicadas {len(lines)}/{NUM_PORTS} líneas ({len(payload)} bytes), "
          f"6 transacciones RMAP.")

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

    print(f"\nServicio HK Esencial iniciado. Sondeando cada {POLL_INTERVAL_SECONDS}s "
          f"(6 transacciones RMAP/ciclo). Ctrl+C para parar.\n")

    transaction_id = 1
    try:
        while _running:
            cycle_start = time.time()

            transaction_id = capture_essential_cycle(channel, mqtt_client, device_serial, transaction_id)

            elapsed = time.time() - cycle_start
            sleep_time = max(0.0, POLL_INTERVAL_SECONDS - elapsed)
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
