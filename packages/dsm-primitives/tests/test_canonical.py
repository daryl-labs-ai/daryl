"""Tests for dsm_primitives.canonical module."""

import json

import pytest

from dsm_primitives import canonical_json


def test_empty_dict():
    assert canonical_json({}) == b"{}"


def test_single_key():
    assert canonical_json({"a": 1}) == b'{"a":1}'


def test_keys_are_sorted():
    result = canonical_json({"b": 1, "a": 2})
    assert result == b'{"a":2,"b":1}'


def test_nested_keys_are_sorted():
    result = canonical_json({"outer": {"z": 1, "a": 2}})
    assert result == b'{"outer":{"a":2,"z":1}}'


def test_no_whitespace():
    result = canonical_json({"a": [1, 2, 3], "b": {"c": "d"}})
    assert b" " not in result


def test_ascii_escaping():
    # "café" must become \u00e9 in output
    result = canonical_json({"s": "café"})
    assert result == b'{"s":"caf\\u00e9"}'


def test_emoji_escaping():
    result = canonical_json({"s": "🎉"})
    # Emoji encoded as surrogate pair in \uXXXX form
    assert b"\\ud83c\\udf89" in result


def test_unicode_line_separator_escaped():
    # U+2028 must be escaped (otherwise breaks JS parsers)
    result = canonical_json({"s": "a\u2028b"})
    assert b"\\u2028" in result


def test_null_value():
    assert canonical_json({"a": None}) == b'{"a":null}'


def test_bool_values():
    assert canonical_json({"t": True, "f": False}) == b'{"f":false,"t":true}'


def test_nan_raises():
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_infinity_raises():
    with pytest.raises(ValueError):
        canonical_json({"x": float("inf")})


def test_bytes_raises():
    with pytest.raises(TypeError):
        canonical_json({"x": b"bytes"})


def test_set_raises():
    with pytest.raises(TypeError):
        canonical_json({"x": {1, 2, 3}})


def test_custom_object_raises():
    class Foo:
        pass
    with pytest.raises(TypeError):
        canonical_json({"x": Foo()})


def test_deterministic():
    # Same input, different dict construction order — same output
    d1 = {"a": 1, "b": 2, "c": 3}
    d2 = {"c": 3, "b": 2, "a": 1}
    assert canonical_json(d1) == canonical_json(d2)
