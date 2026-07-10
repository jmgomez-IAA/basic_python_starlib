"""
register_map.py — Nombres de los registros conocidos del GR718B, extraídos
de la Tabla 8 (Register overview) del manual oficial v3.9, sección 2.4.

Usado únicamente para anotar el volcado de memoria (07_dump_memory.py) con
nombres legibles en lugar de solo direcciones. Los rangos de "routing table"
(RTPMAP/RTACTRL/RTCOMB) tienen una entrada por dirección física/lógica
(demasiadas para listar una a una), así que se etiquetan genéricamente con
su índice dentro del rango.
"""

# Registros de dirección única (nombre exacto)
SINGLE_REGISTERS = {
    0x00000800: "RTR.PCTRLCFG (port control, config port)",
    0x00000880: "RTR.PSTSCFG (port status, config port)",
    0x00000980: "RTR.PCTRL2CFG (port control 2, config port)",
    0x00000A00: "RTR.RTRCFG (router configuration/status)",
    0x00000A04: "RTR.TC (time-code)",
    0x00000A08: "RTR.VER (version/instance ID)",
    0x00000A0C: "RTR.IDIV (initialization divisor)",
    0x00000A10: "RTR.CFGWE (configuration write enable)",
    0x00000A14: "RTR.PRESCALER (timer prescaler reload)",
    0x00000A18: "RTR.IMASK (interrupt mask)",
    0x00000A1C: "RTR.IPMASK (interrupt port mask)",
    0x00000A20: "RTR.PIP (port interrupt pending)",
    0x00000A24: "RTR.ICODEGEN (interrupt code generation)",
    0x00000A28: "RTR.ISR0 (ISR, interrupt 0-31)",
    0x00000A2C: "RTR.ISR1 (ISR, interrupt 32-63)",
    0x00000A30: "RTR.ISRTIMER (ISR timer reload)",
    0x00000A34: "RTR.AITIMER (ACK-to-INT timer reload)",
    0x00000A38: "RTR.ISRCTIMER (ISR change timer reload)",
    0x00000A40: "RTR.LRUNSTS (SpaceWire link running status)",
    0x00000A44: "RTR.CAP (capability)",
    0x00000A50: "RTR.PNPVEND (SpW PnP device vendor/product ID)",
    0x00000A54: "RTR.PNPUVEND (SpW PnP unit vendor/product ID)",
    0x00000A58: "RTR.PNPUSN (SpW PnP unit serial number)",
    0x00000F00: "RTR.GPOA (general purpose out, bits 0-31)",
    0x00000F04: "RTR.GPOB (general purpose out, bits 32-48)",
    0x00000F10: "RTR.GPIA (general purpose in, bits 0-1)",
    0x00002000: "SPI.CAP (capability)",
    0x00002020: "SPI.MODE (mode)",
    0x00002024: "SPI.EVENT (event)",
    0x00002028: "SPI.MASK (mask)",
    0x0000202C: "SPI.CMD (command)",
    0x00002030: "SPI.TX (transmit)",
    0x00002034: "SPI.RX (receive)",
    0x00002038: "SPI.SLVSEL (slave select, optional)",
    0x0000203C: "SPI.ASLVSEL (automatic slave select)",
    0x00002100: "GPIO.DATA (I/O port data)",
    0x00002104: "GPIO.OUT (I/O port output)",
    0x00002108: "GPIO.DIR (I/O port direction)",
    0x0000211C: "GPIO.CAP (capability)",
}

# Rangos por puerto (1-19), 4 bytes por puerto, direcciones RMAP
PORT_RANGES = {
    (0x00000804, 0x0000084C): "RTR.PCTRL (port control, ports 1-19)",
    (0x00000884, 0x000008CC): "RTR.PSTS (port status, ports 1-19)",
    (0x00000900, 0x0000094C): "RTR.PTIMER (port timer reload, ports 0-19)",
    (0x00000984, 0x000009CC): "RTR.PCTRL2 (port control 2, ports 1-19)",
    (0x00000C10, 0x00000D3C): "RTR.[O/I]CHARCNT / [O/I]PKTCNT (traffic counters, ports 1-19, 16B/puerto)",
    (0x00000E00, 0x00000E4C): "RTR.MAXPLEN (maximum packet length, ports 0-19)",
    (0x00000E84, 0x00000EC8): "RTR.CREDCNT (credit counter, ports 1-18)",
}

# Rangos de la tabla de rutado (demasiadas entradas para nombrar una a una)
ROUTING_TABLE_RANGES = {
    (0x00000004, 0x0000004C): "RTR.RTPMAP (routing, físicas 1-19)",
    (0x00000080, 0x000003FC): "RTR.RTPMAP (routing, lógicas 32-255)",
    (0x00000404, 0x0000044C): "RTR.RTACTRL (address control, físicas 1-19)",
    (0x00000480, 0x000007FC): "RTR.RTACTRL (address control, lógicas 32-255)",
    (0x00001004, 0x0000104C): "RTR.RTCOMB (combinado, direcciones 1-19)",
    (0x00001080, 0x000013FC): "RTR.RTCOMB (combinado, direcciones 32-255)",
}


def name_for_address(address: int) -> str:
    """Devuelve una etiqueta legible para una dirección RMAP del GR718B, o
    cadena vacía si no está mapeada (reservado / sin uso)."""
    if address in SINGLE_REGISTERS:
        return SINGLE_REGISTERS[address]

    for (start, end), label in PORT_RANGES.items():
        if start <= address <= end:
            return label

    for (start, end), label in ROUTING_TABLE_RANGES.items():
        if start <= address <= end:
            return label

    if 0x00002200 <= address <= 0x00002FFC:
        return "(reservado, lee 0, escribir no tiene efecto)"

    return ""
