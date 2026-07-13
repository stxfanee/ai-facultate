from __future__ import annotations

from dataclasses import dataclass

from . import constants as c


@dataclass(frozen=True)
class ConversionResult:
    value: float
    from_unit: str
    to_unit: str
    factor: float | None
    formula: str
    note: str = ""

    @property
    def formatted_value(self) -> str:
        return format_number(self.value)


def format_number(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.6g}".replace(",", " ")
    return f"{value:.8g}"


ALIASES = {
    "kw": "kw", "kilowatt": "kw", "kilowatts": "kw",
    "w": "w", "watt": "w", "watts": "w",
    "cp": "metric_hp", "ps": "metric_hp", "cv": "metric_hp",
    "metric horsepower": "metric_hp", "metric hp": "metric_hp",
    "hp": "mechanical_hp", "bhp": "mechanical_hp",
    "mechanical horsepower": "mechanical_hp", "british horsepower": "mechanical_hp", "imperial horsepower": "mechanical_hp",
    "j": "j", "joule": "j", "joules": "j", "kj": "kj", "kwh": "kwh", "wh": "wh", "cal": "cal",
    "pa": "pa", "pascal": "pa", "pascals": "pa", "kpa": "kpa", "bar": "bar", "atm": "atm", "mmhg": "mmhg",
    "c": "c", "celsius": "c", "degc": "c", "f": "f", "fahrenheit": "f", "degf": "f", "k": "k", "kelvin": "k",
    "m": "m", "meter": "m", "metre": "m", "km": "km", "cm": "cm", "mm": "mm", "in": "in", "inch": "in", "ft": "ft", "foot": "ft", "feet": "ft", "mi": "mi", "mile": "mi",
    "kg": "kg", "kilogram": "kg", "g": "g", "gram": "g", "mg": "mg", "lb": "lb", "pound": "lb",
    "m/s": "m/s", "ms": "m/s", "km/h": "km/h", "kmh": "km/h", "mph": "mph",
    "s": "s", "sec": "s", "second": "s", "min": "min", "minute": "min", "h": "h", "hr": "h", "hour": "h",
}

POWER_TO_KW = {"kw": 1.0, "w": 0.001, "metric_hp": c.METRIC_HORSEPOWER_KW, "mechanical_hp": c.MECHANICAL_HORSEPOWER_KW}
ENERGY_TO_J = {"j": 1.0, "kj": 1000.0, "wh": 3600.0, "kwh": c.JOULE_PER_KWH, "cal": c.CALORIE_J}
PRESSURE_TO_PA = {"pa": 1.0, "kpa": 1000.0, "bar": c.PASCAL_PER_BAR, "atm": c.ATM_PA, "mmhg": c.MMHG_PA}
LENGTH_TO_M = {"m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "in": c.INCH_M, "ft": c.FOOT_M, "mi": c.MILE_M}
MASS_TO_KG = {"kg": 1.0, "g": 0.001, "mg": 0.000001, "lb": c.POUND_KG}
SPEED_TO_MPS = {"m/s": 1.0, "km/h": c.METER_PER_KILOMETER / c.SECOND_PER_HOUR, "mph": c.MILE_M / c.SECOND_PER_HOUR}
TIME_TO_S = {"s": 1.0, "min": 60.0, "h": 3600.0}
GROUPS = [POWER_TO_KW, ENERGY_TO_J, PRESSURE_TO_PA, LENGTH_TO_M, MASS_TO_KG, SPEED_TO_MPS, TIME_TO_S]
DISPLAY = {
    "kw": "kW", "w": "W", "metric_hp": "CP/PS", "mechanical_hp": "hp",
    "j": "J", "kj": "kJ", "wh": "Wh", "kwh": "kWh", "cal": "cal",
    "pa": "Pa", "kpa": "kPa", "bar": "bar", "atm": "atm", "mmhg": "mmHg",
    "c": "C", "f": "F", "k": "K",
    "m": "m", "km": "km", "cm": "cm", "mm": "mm", "in": "in", "ft": "ft", "mi": "mi",
    "kg": "kg", "g": "g", "mg": "mg", "lb": "lb",
    "m/s": "m/s", "km/h": "km/h", "mph": "mph", "s": "s", "min": "min", "h": "h",
}


def normalize_unit(unit: str) -> str:
    cleaned = unit.strip().lower().replace("°", "deg")
    if cleaned in ALIASES:
        return ALIASES[cleaned]
    raise ValueError(f"Unitate necunoscuta: {unit}")


def unit_note(unit: str) -> str:
    if unit == "metric_hp":
        return "CP si PS sunt horsepower metric; CV este folosit similar in unele limbi."
    if unit == "mechanical_hp":
        return "hp este horsepower mecanic/imperial, diferit de CP/PS."
    return ""


def convert_temperature(value: float, source: str, target: str) -> ConversionResult:
    if source == target:
        result = value; formula = f"{format_number(value)} {DISPLAY[source]} = {format_number(result)} {DISPLAY[target]}"
    elif source == "c" and target == "f":
        result = value * 9 / 5 + 32; formula = "F = C x 9/5 + 32"
    elif source == "f" and target == "c":
        result = (value - 32) * 5 / 9; formula = "C = (F - 32) x 5/9"
    elif source == "c" and target == "k":
        result = value + 273.15; formula = "K = C + 273.15"
    elif source == "k" and target == "c":
        result = value - 273.15; formula = "C = K - 273.15"
    elif source == "f" and target == "k":
        result = (value - 32) * 5 / 9 + 273.15; formula = "K = (F - 32) x 5/9 + 273.15"
    elif source == "k" and target == "f":
        result = (value - 273.15) * 9 / 5 + 32; formula = "F = (K - 273.15) x 9/5 + 32"
    else:
        raise ValueError("Conversie de temperatura invalida")
    return ConversionResult(result, DISPLAY[source], DISPLAY[target], None, formula)


def convert(value: float, from_unit: str, to_unit: str) -> ConversionResult:
    source = normalize_unit(from_unit)
    target = normalize_unit(to_unit)
    if source in {"c", "f", "k"} or target in {"c", "f", "k"}:
        if source not in {"c", "f", "k"} or target not in {"c", "f", "k"}:
            raise ValueError("Temperatura se poate converti doar intre C, F si K")
        return convert_temperature(value, source, target)
    for group in GROUPS:
        if source in group and target in group:
            base = value * group[source]
            result = base / group[target]
            factor = group[source] / group[target]
            formula = f"{DISPLAY[target]} = {DISPLAY[source]} x {format_number(factor)}"
            note = " ".join(x for x in (unit_note(source), unit_note(target)) if x)
            return ConversionResult(result, DISPLAY[source], DISPLAY[target], factor, formula, note)
    raise ValueError(f"Nu pot converti intre {from_unit} si {to_unit}")


def horsepower_reference() -> dict:
    return {
        "metric_hp_kw": c.METRIC_HORSEPOWER_KW,
        "kw_metric_hp": 1 / c.METRIC_HORSEPOWER_KW,
        "mechanical_hp_kw": c.MECHANICAL_HORSEPOWER_KW,
        "kw_mechanical_hp": 1 / c.MECHANICAL_HORSEPOWER_KW,
    }


def horsepower_explanation() -> str:
    ref = horsepower_reference()
    return (
        "CP si PS inseamna horsepower metric.\n"
        f"1 CP = 1 PS ~= {ref['metric_hp_kw']:.8f} kW, deci 1 kW ~= {ref['kw_metric_hp']:.7f} CP/PS.\n"
        "hp (British/mechanical horsepower) este diferit.\n"
        f"1 hp ~= {ref['mechanical_hp_kw']:.8f} kW, deci 1 kW ~= {ref['kw_mechanical_hp']:.7f} hp."
    )
