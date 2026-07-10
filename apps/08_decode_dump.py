#!/usr/bin/env python3
"""
08_decode_dump.py — Genera un informe legible decodificando bit a bit
RTR.LRUNSTS y RTR.PSTS (todos los puertos) a partir de un volcado ya
generado por 07_dump_memory.py (gr718b_dump.bin).

No necesita hardware conectado: trabaja sobre el fichero binario.

Uso:
    python apps/08_decode_dump.py [ruta_al_dump.bin]
    (por defecto: gr718b_dump.bin en el directorio actual)
"""

import sys
import struct

import decode_registers as dr

DUMP_START_ADDRESS = 0x00000000

LRUNSTS_ADDRESS = 0x00000A40
PSTS_BASE_ADDRESS = 0x00000884
NUM_PORTS = 19  # 1-18 SpaceWire, 19 = SIST


def read_u32_at(dump: bytes, address: int) -> int:
    offset = address - DUMP_START_ADDRESS
    return struct.unpack(">I", dump[offset:offset + 4])[0]  # big-endian (orden RMAP)


def main():
    dump_path = sys.argv[1] if len(sys.argv) > 1 else "gr718b_dump.bin"

    try:
        with open(dump_path, "rb") as f:
            dump = f.read()
    except FileNotFoundError:
        print(f"No se encuentra {dump_path}. Ejecuta antes 07_dump_memory.py.")
        sys.exit(1)

    print("=" * 70)
    print("RTR.LRUNSTS — Estado de enlace por puerto (Tabla 48)")
    print("=" * 70)
    lrunsts_raw = read_u32_at(dump, LRUNSTS_ADDRESS)
    print(f"Valor crudo: 0x{lrunsts_raw:08X}\n")
    running = dr.decode_lrunsts(lrunsts_raw)
    for port in range(1, 19):
        estado = "RUN" if running[port] else "no-run"
        print(f"  Puerto {port:2d}: {estado}")

    print()
    print("=" * 70)
    print("RTR.PSTS — Estado detallado por puerto (Tabla 29)")
    print("=" * 70)

    puertos_con_error = []

    for port in range(1, NUM_PORTS + 1):
        address = PSTS_BASE_ADDRESS + (port - 1) * 4
        raw = read_u32_at(dump, address)
        status = dr.decode_psts(raw, port)

        print(f"\n--- Puerto {port} ({status.port_type}) — 0x{address:08X} = 0x{raw:08X} ---")
        print(f"  Link state:            {status.link_state}")
        print(f"  Active status:         {status.active_status}")
        print(f"  Port receive busy:     {status.port_receive_busy}")
        print(f"  Port transmit busy:    {status.port_transmit_busy}")
        print(f"  Transmit FIFO full:    {status.transmit_fifo_full}")
        print(f"  Receive FIFO empty:    {status.receive_fifo_empty}")
        print(f"  Input port (último):   {status.input_port}")

        errores = []
        if status.invalid_address_error:
            errores.append("invalid_address")
        if status.credit_error:
            errores.append("credit")
        if status.escape_error:
            errores.append("escape")
        if status.disconnect_error:
            errores.append("disconnect")
        if status.parity_error:
            errores.append("parity")

        if errores:
            print(f"  *** ERRORES ACTIVOS: {', '.join(errores)} ***")
            puertos_con_error.append((port, errores))
        else:
            print("  Errores:               ninguno")

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    puertos_run = [p for p in range(1, 19) if running[p]]
    print(f"Puertos en RUN: {puertos_run if puertos_run else '(ninguno)'}")
    if puertos_con_error:
        print("Puertos con algún bit de error activo:")
        for port, errores in puertos_con_error:
            print(f"  Puerto {port}: {', '.join(errores)}")
    else:
        print("Ningún puerto reporta bits de error activos.")


if __name__ == "__main__":
    main()
