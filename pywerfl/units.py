"""Unit conversion registry"""

from __future__ import annotations

_FACTORS = {
    ("mph", "m/s"): 0.44704,
    ("inHg", "kPa"): 3.386389,
    ("psf", "kPa"): 0.0478803,
    ("slug/ft3", "kg/m3"): 515.379,
    ("ft", "m"): 0.3048,
    ("fraction", "%"): 100,
    ("%", "fraction"): 0.01,
}

def convert(values, from_unit: str, to_unit: str):
    if from_unit == to_unit:
        return values
    if from_unit == "degF" and to_unit == "K":
        return (values - 32) * (5 / 9) + 273.15
    try:
        return values * _FACTORS[(from_unit, to_unit)]
    except KeyError:
        raise ValueError(f"no conversion registered from {from_unit!r} to {to_unit!r}") from None
