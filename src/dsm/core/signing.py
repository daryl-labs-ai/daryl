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
DSM v2 - Signing Module
SHA-256 hash chain for append-only integrity.
Verification uses same canonical entry hash as storage (session_id, source, timestamp, metadata, content, prev_hash).
"""

import hashlib
from typing import Optional, List
from datetime import datetime

from .storage import _compute_canonical_entry_hash


class Signing:
    """Gestion de signature et chaîne de hachage"""

    @staticmethod
    def compute_hash(content: str) -> str:
        """Calcule le hash SHA-256 (content-only; legacy). Préférer hash canonique pour nouvelles entrées."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    @staticmethod
    def verify_chain(entries: list) -> dict:
        """
        Vérifie la chaîne de hachage (hash canonique: session_id, source, timestamp, metadata, content, prev_hash).

        Args:
            entries: Liste d'entrées à vérifier

        Returns:
            dict: Métriques de vérification
        """
        verified = 0
        corrupted = 0
        tampering_detected = 0
        last_valid_hash = None

        for i, entry in enumerate(entries):
            if entry.prev_hash and last_valid_hash:
                if entry.prev_hash != last_valid_hash:
                    corrupted += 1
                else:
                    verified += 1

            if entry.hash:
                try:
                    recalculated = _compute_canonical_entry_hash(entry, entry.prev_hash)
                    if recalculated != entry.hash:
                        tampering_detected += 1
                except Exception:
                    pass

            last_valid_hash = entry.hash if entry.hash else last_valid_hash

        total = verified + corrupted + tampering_detected

        return {
            "total": total,
            "verified": verified,
            "corrupted": corrupted,
            "tampering_detected": tampering_detected,
            "verification_rate": (verified / total * 100) if total > 0 else 0
        }

    @staticmethod
    def chain_entry(new_content: str, prev_hash: Optional[str]) -> dict:
        """
        Crée une nouvelle entrée avec chaîne de hachage

        Args:
            new_content: Contenu à signer
            prev_hash: Hash de l'entrée précédente

        Returns:
            dict: Entrée avec hash et prev_hash
        """
        hash = Signing.compute_hash(new_content)

        return {
            "hash": hash,
            "prev_hash": prev_hash,
            "content": new_content
        }
