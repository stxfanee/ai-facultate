from __future__ import annotations

from .unit_converter import ConversionResult, convert


def calculate_conversion(value: float, from_unit: str, to_unit: str) -> ConversionResult:
    return convert(value, from_unit, to_unit)

