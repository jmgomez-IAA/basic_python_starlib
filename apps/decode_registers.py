"""
decode_registers.py — Decodificación bit a bit de RTR.LRUNSTS y RTR.PSTS,
según las Tablas 48 y 29 (respectivamente) del manual GR718B v3.9,
Oct 2024, sección 6.5.3. Verificado directamente contra el texto del PDF
oficial (no inferido).
"""

from dataclasses import dataclass, field
from typing import Optional


def _bits(value: int, high: int, low: int) -> int:
    """Extrae los bits [high:low] (inclusive) de `value`."""
    mask = (1 << (high - low + 1)) - 1
    return (value >> low) & mask


LINK_STATE_NAMES = {
    0b000: "Error reset",
    0b001: "Error wait",
    0b010: "Ready",
    0b011: "Started",
    0b100: "Connecting",
    0b101: "Run state",
}


def decode_lrunsts(raw_value: int) -> dict:
    """
    Decodifica RTR.LRUNSTS (0x00000A40), Tabla 48.
    Bits 18:1 -> bit N = puerto N en estado 'run' (N = 1..18). Bit 0 reservado.
    Devuelve {puerto: bool_running} para los puertos 1-18.
    """
    return {port: bool(raw_value & (1 << port)) for port in range(1, 19)}


@dataclass
class PortStatus:
    port: int
    raw_value: int
    port_type: str
    packet_length_truncation: bool
    timecode_truncation: bool
    rmap_pnp_spill: bool
    spill_if_not_ready_spill: bool
    link_start_on_request_status: Optional[bool]
    spill_status: bool
    active_status: bool
    timeout_spill: bool
    transmit_fifo_full: bool
    receive_fifo_empty: bool
    link_state: Optional[str]
    input_port: int
    port_receive_busy: bool
    port_transmit_busy: bool
    invalid_address_error: bool
    credit_error: Optional[bool]
    escape_error: Optional[bool]
    disconnect_error: Optional[bool]
    parity_error: Optional[bool]

    def has_any_error(self) -> bool:
        errores = [
            self.invalid_address_error,
            self.credit_error,
            self.escape_error,
            self.disconnect_error,
            self.parity_error,
        ]
        return any(bool(e) for e in errores if e is not None)


def decode_psts(raw_value: int, port: int) -> PortStatus:
    """
    Decodifica RTR.PSTS para un puerto (1-19), Tabla 29 (0x00000884-0x000008CC).
    El puerto 19 es el puerto SIST: los campos marcados en el manual como
    "solo disponible para puertos SpaceWire" se devuelven como None para él.
    """
    is_spw_port = 1 <= port <= 18

    pt_bits = _bits(raw_value, 31, 30)
    port_type = "SIST" if pt_bits == 0b11 else "SpaceWire"

    ls_bits = _bits(raw_value, 14, 12)
    link_state = LINK_STATE_NAMES.get(ls_bits) if is_spw_port else None

    return PortStatus(
        port=port,
        raw_value=raw_value,
        port_type=port_type,
        packet_length_truncation=bool(_bits(raw_value, 29, 29)),
        timecode_truncation=bool(_bits(raw_value, 28, 28)),
        rmap_pnp_spill=bool(_bits(raw_value, 27, 27)),
        spill_if_not_ready_spill=bool(_bits(raw_value, 26, 26)),
        link_start_on_request_status=bool(_bits(raw_value, 22, 22)) if is_spw_port else None,
        spill_status=bool(_bits(raw_value, 21, 21)),
        active_status=bool(_bits(raw_value, 20, 20)),
        timeout_spill=bool(_bits(raw_value, 18, 18)),
        transmit_fifo_full=bool(_bits(raw_value, 16, 16)),
        receive_fifo_empty=bool(_bits(raw_value, 15, 15)),
        link_state=link_state,
        input_port=_bits(raw_value, 11, 7),
        port_receive_busy=bool(_bits(raw_value, 6, 6)),
        port_transmit_busy=bool(_bits(raw_value, 5, 5)),
        invalid_address_error=bool(_bits(raw_value, 4, 4)),
        credit_error=bool(_bits(raw_value, 3, 3)) if is_spw_port else None,
        escape_error=bool(_bits(raw_value, 2, 2)) if is_spw_port else None,
        disconnect_error=bool(_bits(raw_value, 1, 1)) if is_spw_port else None,
        parity_error=bool(_bits(raw_value, 0, 0)) if is_spw_port else None,
    )
