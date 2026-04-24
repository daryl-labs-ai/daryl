"""Canonical JSON serialization for hashing.

Per ADR-0002 v1 spec:
  - sort_keys=True
  - separators=(",", ":")
  - ensure_ascii=True
  - allow_nan=False
  - encoding=UTF-8
  - Unsupported types raise TypeError (no implicit coercion)
  - Callers responsible for NFC normalization of strings
"""

import json


def canonical_json(data: dict) -> bytes:
    """Serialize a dict to canonical JSON bytes.

    Args:
        data: A dict containing only JSON-native types (str, int, float,
            bool, None, list, dict). Strings should be NFC-normalized.

    Returns:
        UTF-8 encoded canonical JSON bytes.

    Raises:
        TypeError: if data contains values not natively serializable by
            json.dumps (e.g. bytes, datetime, set, custom objects).
        ValueError: if data contains NaN or Infinity.
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
