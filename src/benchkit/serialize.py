"""Serialization utilities for BenchKit."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias

Scalar: TypeAlias = str | int | float | bool | None

Serializer: TypeAlias = Callable[[Any], dict[str, Scalar] | Scalar]


def serialize(data: dict[str, Any], serializers: dict[type, Serializer]) -> dict[str, Scalar]:
    """Serialize data using the provided serializers.

    Args:
        data (dict[str, Any]): Inputs to serialize.
        serializers (dict[type, Serializer]): Mapping from types to serialization functions.

    Returns:
        dict[str, Scalar]: Serialized data as a dictionary.
    """
    serialized = {}
    for key, value in data.items():
        serialized.update(_safe_serialize(key, value, serializers))
    return serialized


def _safe_serialize(arg_name: str, val: object, serializers: dict[type, Serializer]) -> dict[str, Scalar]:
    """Safely serialize a value using the provided serializers.

    Args:
        arg_name (str): Name of the argument being serialized.
        val (object): Value to serialize.
        serializers (dict[type, Serializer]): Mapping from types to serialization functions.

    Returns:
        dict[str, Scalar]: Serialized value as a dictionary.

    Raises:
        TypeError: If the value cannot be serialized.
    """
    if isinstance(val, Scalar):
        return {arg_name: val}

    for type_, serializer in serializers.items():
        if isinstance(val, type_):
            val = serializer(val)

    if isinstance(val, dict):
        flat_dict = _flatten_dict(val, prefix=arg_name + "_")
        if any(not isinstance(v, Scalar) for v in flat_dict.values()):
            msg = f"Cannot serialize nested type for argument '{arg_name}'."
            raise TypeError(msg)
        return flat_dict

    msg = f"Unsupported type for argument '{arg_name}': {type(val)}"
    raise TypeError(msg)


def _flatten_dict(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a nested dictionary with prefixed keys.

    Args:
        d (dict[str, Any]): Dictionary to flatten.
        prefix (str): Prefix for the keys.

    Returns:
        dict[str, Any]: Flattened dictionary with prefixed keys.
    """
    flattened = {}
    for key, value in d.items():
        new_key = f"{prefix}{key}"
        if isinstance(value, dict):
            flattened.update(_flatten_dict(value, f"{new_key}_"))
        else:
            flattened[new_key] = value
    return flattened
