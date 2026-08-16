"""
Input receipt utilities for DSM.

Agents use these helpers to hash external responses before logging them with
confirm_action(). A receipt binds the CALLER-SUPPLIED input bytes to the
recorded result.

Capture boundary — read this before relying on a receipt as evidence:

    A receipt hashes the bytes it is handed. It does NOT establish that those
    bytes are what the agent or model actually observed. If a caller reads a
    source file and then passes a summary of it to make_receipt(), the receipt
    is internally consistent and will verify as INTACT — faithfully, because it
    binds exactly what it was given.

    Detecting that substitution requires the true material to be available and
    compared explicitly against the recorded input_hash. DSM cannot do that on
    its own; it would need an instrumentation/runtime boundary that captures
    the input at the point of consumption.
"""

import hashlib
import json
from typing import Union


def hash_input(data: Union[str, bytes, dict]) -> str:
    """
    Compute SHA-256 hex digest of an external input.

    Accepts:
    - str: hashed as UTF-8 bytes
    - bytes: hashed directly
    - dict: serialized to sorted JSON, then hashed

    Returns hex digest string.
    """
    if isinstance(data, dict):
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    elif isinstance(data, str):
        raw = data.encode("utf-8")
    elif isinstance(data, bytes):
        raw = data
    else:
        raw = str(data).encode("utf-8")

    return hashlib.sha256(raw).hexdigest()


def make_receipt(
    response_data: Union[str, bytes, dict],
    preview_length: int = 200,
) -> dict:
    """
    Create an input receipt dict ready to pass to confirm_action.

    Returns:
        {"input_hash": "abc123...", "input_preview": "first 200 chars..."}

    Usage:
        receipt = make_receipt(api_response.text)
        session.confirm_action(intent_id, result_data, **receipt)
    """
    h = hash_input(response_data)

    if isinstance(response_data, bytes):
        preview = response_data[:preview_length].decode("utf-8", errors="replace")
    elif isinstance(response_data, dict):
        preview = json.dumps(response_data, ensure_ascii=False)[:preview_length]
    else:
        preview = str(response_data)[:preview_length]

    return {
        "input_hash": h,
        "input_preview": preview,
    }
