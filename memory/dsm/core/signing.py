#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Signing Module
SHA-256 hash chain for append-only integrity
"""

import hashlib
from typing import Optional, List
from datetime import datetime

class Signing:
    """Gestion de signature et chaîne de hachage"""

    @staticmethod
    def compute_hash(content: str) -> str:
        """Calcule le hash SHA-256"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    @staticmethod
    def verify_chain(entries: list) -> dict:
        """
        Vérifie la chaîne de hachage

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
                    # Recalculate hash from content
                    recalculated = Signing.compute_hash(entry.content)
                    if recalculated != entry.hash:
                        tampering_detected += 1
                except:
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
