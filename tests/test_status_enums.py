"""Tests for status enum backward compatibility."""
from dsm.status import VerifyStatus, SealStatus, ReceiptStatus, WitnessStatus


def test_verify_status_string_compat():
    assert VerifyStatus.OK == "OK"
    assert VerifyStatus.TAMPERED == "TAMPERED"


def test_seal_status_string_compat():
    assert SealStatus.VALID == "VALID"
    assert SealStatus.HASH_MISMATCH == "HASH_MISMATCH"


def test_receipt_status_string_compat():
    assert ReceiptStatus.INTACT == "INTACT"
    assert ReceiptStatus.TAMPERED == "TAMPERED"
    assert ReceiptStatus.SIGNATURE_INVALID == "SIGNATURE_INVALID"


def test_witness_status_string_compat():
    assert WitnessStatus.OK == "OK"
    assert WitnessStatus.DIVERGED == "DIVERGED"
