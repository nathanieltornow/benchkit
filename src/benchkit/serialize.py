"""Serialization utilities for BenchKit."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias

Serializer: TypeAlias = Callable[[Any], dict[str, Any]]


def serialize(data: dict[str, Any], serializers: dict[type, Serializer]) -> dict[str, Any]:
    """Serialize data using the provided serializers.

    Args:
        data (dict[str, Any]): Inputs to serialize.
        serializers (dict[type, Serializer]): Mapping from types to serialization functions.

    Returns:
        dict[str, Any]: Serialized data as a dictionary.
    """
    serialized = {}
    for key, value in data.items():
        serialized.update(_serialize_argument(key, value, serializers))
    return serialized


def _serialize_argument(arg_name: str, val: object, serializers: dict[type, Serializer]) -> dict[str, Any]:
    """Safely serialize a value using the provided serializers.

    Args:
        arg_name (str): Name of the argument being serialized.
        val (object): Value to serialize.
        serializers (dict[type, Serializer]): Mapping from types to serialization functions.

    Returns:
        dict[str, Any] | object: Serialized value as a dictionary or a scalar value.
    """
    for type_, serializer in serializers.items():
        if isinstance(val, type_):
            val = serializer(val)
            return {f"{arg_name}_{k}": v for k, v in val.items()}

    return {arg_name: val}
