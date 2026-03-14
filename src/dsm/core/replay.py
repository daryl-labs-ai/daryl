#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM Kernel — Frozen Module

This file is part of the DSM storage kernel freeze (March 2026).

The kernel is considered stable and audited.

Modifications must follow the DSM kernel evolution process
and should not be changed casually.

See:
docs/architecture/DSM_KERNEL_FREEZE_2026_03.md
"""
"""
DSM v2 - Replay Module
Trace Replay Functionality
"""

import json
import hashlib
import sys
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, asdict


@dataclass
class ReplayReport:
    """Rapport de replay de trace"""
    session_id: str
    total_records: int
    verified_records: int
    corrupt_records: int
    missing_hash_records: int
    broken_chain_records: int
    first_timestamp: Optional[str]
    last_timestamp: Optional[str]
    status: str  # OK / DIVERGENCE / CORRUPT
    errors: List[str]


@dataclass
class TraceRecord:
    """Enregistrement de trace"""
    trace_id: str
    ts: str
    session_id: str
    action_type: str
    intent: str
    ok: bool
    error: Optional[str]
    state_before: Optional[str]
    state_after: Optional[str]
    prev_step_hash: Optional[str]
    step_hash: str
    raw_line: str
    line_number: int


def parse_trace_line(line: str, line_number: int) -> Optional[TraceRecord]:
    """
    Parse une ligne de trace et retourne un TraceRecord.

    Returns None si la ligne est vide ou invalide.
    """
    line = line.strip()
    if not line:
        return None

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    # Champs requis
    required_fields = ["trace_id", "ts", "session_id", "action_type", "ok", "step_hash"]
    for field in required_fields:
        if field not in data:
            return None

    return TraceRecord(
        trace_id=data["trace_id"],
        ts=data["ts"],
        session_id=data["session_id"],
        action_type=data["action_type"],
        intent=data.get("intent", ""),
        ok=data["ok"],
        error=data.get("error"),
        state_before=data.get("state_before"),
        state_after=data.get("state_after"),
        prev_step_hash=data.get("prev_step_hash"),
        step_hash=data["step_hash"],
        raw_line=line,
        line_number=line_number,
    )


def canonical_json(data: dict) -> str:
    """Retourne une représentation JSON canonique (triée, stable)"""
    return json.dumps(data, sort_keys=True, separators=(',', ':'))


def compute_step_hash(data: dict) -> str:
    """Calcule le hash d'un step de trace"""
    data_str = canonical_json(data)
    return hashlib.sha256(data_str.encode('utf-8')).hexdigest()


def verify_record(record: TraceRecord, strict: bool = False) -> tuple[bool, Optional[str]]:
    """
    Vérifie un enregistrement de trace.

    Returns: (is_valid, error_message)
    """
    # Recompute step_hash from record WITHOUT the step_hash field (avoid self-reference)
    try:
        raw_data = json.loads(record.raw_line)
        hash_input = dict(raw_data)
        hash_input.pop("step_hash", None)
        computed_hash = compute_step_hash(hash_input)
        stored_hash = raw_data.get("step_hash")

        if strict and computed_hash != stored_hash:
            return False, f"step_hash mismatch: computed={computed_hash[:16]}, stored={stored_hash[:16] if stored_hash else 'None'}"

        if not strict and computed_hash != stored_hash:
            return True, f"step_hash mismatch: {stored_hash[:16] if stored_hash else 'None'} != {computed_hash[:16]}"
    except Exception as e:
        return False, f"step_hash computation error: {e}"

    # Vérifier les champs requis
    if not record.trace_id or record.trace_id == "":
        return False, "missing or empty trace_id"

    if not record.session_id or record.session_id == "":
        return False, "missing or empty session_id"

    if not record.action_type:
        return False, "missing action_type"

    return True, None


def verify_chain(records: List[TraceRecord]) -> List[str]:
    """
    Vérifie la chaîne de hash prev_step_hash -> step_hash.

    Returns: list of error messages
    """
    errors = []
    previous_step_hash: Optional[str] = None

    for i, record in enumerate(records):
        # Vérifier prev_step_hash
        if i == 0:
            # Premier record: prev_step_hash doit être null ou vide
            if record.prev_step_hash not in [None, ""]:
                errors.append(f"line {record.line_number}: first record has non-null prev_step_hash")
        else:
            # Records suivants: prev_step_hash doit correspondre au step_hash précédent
            if previous_step_hash is None:
                errors.append(f"line {record.line_number}: missing previous step_hash for comparison")
            elif record.prev_step_hash != previous_step_hash:
                errors.append(
                    f"line {record.line_number}: broken chain - prev_step_hash={record.prev_step_hash if record.prev_step_hash else 'None'} "
                    f"!= previous step_hash={previous_step_hash if previous_step_hash else 'None'}"
                )

        previous_step_hash = record.step_hash

    return errors


def replay_session(
    trace_file: Path,
    session_id: str,
    strict: bool = False,
    limit: Optional[int] = None,
) -> ReplayReport:
    """
    Rejoue une session de trace (audit-only).

    Args:
        trace_file: Chemin vers trace_log.jsonl
        session_id: ID de la session à rejouer
        strict: Si True, toute divergence de hash = CORRUPT
        limit: Limite de records à vérifier (None = tous)

    Returns:
        ReplayReport avec le résultat
    """
    if not trace_file.exists():
        raise FileNotFoundError(f"Trace file not found: {trace_file}")

    records: List[TraceRecord] = []
    errors: List[str] = []
    corrupt_count = 0
    missing_hash_count = 0

    # Lire et parser chaque ligne
    line_number = 0
    for line in trace_file.read_text().split("\n"):
        line_number += 1

        # Parser la ligne
        record = parse_trace_line(line, line_number)
        if record is None:
            if line.strip():
                # Ligne non vide mais invalide
                corrupt_count += 1
                errors.append(f"line {line_number}: corrupted JSON or missing required fields")
            continue

        # Filtrer par session_id
        if record.session_id != session_id:
            continue

        # Vérifier le record
        is_valid, error_msg = verify_record(record, strict=strict)
        if not is_valid and strict:
            corrupt_count += 1
            errors.append(f"line {record.line_number}: {error_msg}")
            continue
        elif not is_valid:
            missing_hash_count += 1
            errors.append(f"line {record.line_number}: WARNING - {error_msg}")
            continue

        records.append(record)

    # Limiter le nombre de records si demandé
    if limit and len(records) > limit:
        records = records[:limit]

    # Vérifier la chaîne de hash
    chain_errors = verify_chain(records)
    errors.extend(chain_errors)
    broken_chain_count = len(chain_errors)

    # Déterminer le statut final
    if corrupt_count > 0:
        status = "CORRUPT"
    elif broken_chain_count > 0:
        status = "DIVERGENCE"
    else:
        status = "OK"

    # Timestamps
    first_timestamp = records[0].ts if records else None
    last_timestamp = records[-1].ts if records else None

    return ReplayReport(
        session_id=session_id,
        total_records=len(records),
        verified_records=len(records) - broken_chain_count,
        corrupt_records=corrupt_count,
        missing_hash_records=missing_hash_count,
        broken_chain_records=broken_chain_count,
        first_timestamp=first_timestamp,
        last_timestamp=last_timestamp,
        status=status,
        errors=errors,
    )


def print_report(report: ReplayReport):
    """Affiche le rapport humain"""
    print("\n" + "=" * 70)
    print(f"DSM v3.0a - Trace Replay Report")
    print("=" * 70)
    print(f"\n📊 Session ID: {report.session_id}")
    print(f"📈 Total Records: {report.total_records}")
    print(f"✅ Verified Records: {report.verified_records}")
    print(f"❌ Corrupt Records: {report.corrupt_records}")
    print(f"⚠️  Missing Hash Records: {report.missing_hash_records}")
    print(f"🔗 Broken Chain Records: {report.broken_chain_records}")
    print(f"\n🕐 First Timestamp: {report.first_timestamp or 'N/A'}")
    print(f"🕐 Last Timestamp: {report.last_timestamp or 'N/A'}")
    print(f"\n📋 Final Status: {report.status}")
    print("=" * 70)

    if report.errors:
        print(f"\n⚠️  Errors ({len(report.errors)}):")
        for error in report.errors[:20]:  # Limiter à 20 erreurs
            print(f"   - {error}")
        if len(report.errors) > 20:
            print(f"   ... and {len(report.errors) - 20} more errors")
    else:
        print("\n✅ No errors found - trace is valid")


def save_json_report(report: ReplayReport, output_dir: Path):
    """Sauvegarde le rapport JSON"""
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"replay_{report.session_id}.json"

    report_dict = {
        "session_id": report.session_id,
        "total_records": report.total_records,
        "verified_records": report.verified_records,
        "corrupt_records": report.corrupt_records,
        "missing_hash_records": report.missing_hash_records,
        "broken_chain_records": report.broken_chain_records,
        "first_timestamp": report.first_timestamp,
        "last_timestamp": report.last_timestamp,
        "status": report.status,
        "errors": report.errors,
    }

    output_file.write_text(json.dumps(report_dict, indent=2, ensure_ascii=False))
    print(f"\n📄 JSON report saved to: {output_file}")


def main():
    """Point d'entrée principal (CLI)"""
    import argparse

    parser = argparse.ArgumentParser(description="DSM v3.0a - Trace Replay (Audit-Only)")
    parser.add_argument("--session", required=True, help="Session ID to replay")
    parser.add_argument("--strict", action="store_true", help="Strict mode: any hash mismatch = CORRUPT")
    parser.add_argument("--limit", type=int, help="Limit number of records to verify")
    parser.add_argument("--trace-file", default="data/traces/trace_log.jsonl", help="Path to trace log file")
    parser.add_argument("--output-dir", default="data/diagnostics", help="Output directory for JSON report")

    args = parser.parse_args()

    trace_file = Path(args.trace_file)

    try:
        report = replay_session(
            trace_file=trace_file,
            session_id=args.session,
            strict=args.strict,
            limit=args.limit,
        )

        print_report(report)

        # Sauvegarder le rapport JSON
        output_dir = Path(args.output_dir)
        save_json_report(report, output_dir)

        # Code de sortie
        if report.status == "OK":
            sys.exit(0)
        elif report.status == "DIVERGENCE":
            sys.exit(2)
        else:  # CORRUPT
            sys.exit(3)

    except FileNotFoundError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
