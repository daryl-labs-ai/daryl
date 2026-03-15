#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Session Limits Manager (V2)
Gestion du cooldown et rate limiting pour DSM Session Graph
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple


class SessionLimitsManager:
    """Gestionnaire des limites de session DSM"""

    def __init__(self, base_dir: str = None):
        """
        Initialise le gestionnaire de limites

        Args:
            base_dir: Répertoire DSM (optionnel)
        """
        # Configuration du répertoire
        if base_dir is None:
            base_dir = str(Path.home() / "clawdbot_dsm_test" / "memory")

        self.base_dir = Path(base_dir)
        self.index_dir = self.base_dir / "index"
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Fichier d'état
        self.state_file = self.index_dir / "session_limits.json"

        # Limites de configuration
        self.HOME_POLL_COOLDOWN = 30  # Secondes
        self.ACTION_COOLDOWN = 120  # Secondes
        self.DAILY_ACTION_BUDGET = 10  # Actions max par jour
        self.PER_CYCLE_BUDGET = 1  # Actions max par cycle

    @classmethod
    def agent_defaults(cls, base_dir: str):
        """
        Recommended limits for autonomous agents.

        Removes human-oriented cooldowns so agents can perform
        multiple actions per session without being blocked.
        """
        limits = cls(base_dir=base_dir)
        limits.ACTION_COOLDOWN = 0
        limits.POLL_INTERVAL = 1
        return limits

    # ============================================================================
    # CHEMINS & FICHIERS
    # ============================================================================

    def get_state_path(self) -> Path:
        """
        Retourne le chemin vers le fichier d'état

        Returns:
            Path: Chemin complet
        """
        return self.state_file

    def _load_state(self) -> Dict[str, Any]:
        """
        Charge l'état depuis le fichier

        Returns:
            dict: État actuel (défauts si fichier inexistant)
        """
        if not self.state_file.exists():
            # État initial par défaut
            return self._get_default_state()

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                return state
        except Exception as e:
            print(f"❌ Erreur chargement état: {e}")
            return self._get_default_state()

    def _get_default_state(self) -> Dict[str, Any]:
        """Retourne l'état par défaut"""
        return {
            "last_home_poll_ts": 0,
            "last_action_ts": 0,
            "actions_today_count": 0,
            "actions_today_date": (datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            "skipped_home_polls": 0,
            "skipped_actions_cooldown": 0,
            "skipped_actions_daily_limit": 0
        }

    def _save_state(self, state: Dict[str, Any]) -> bool:
        """
        Sauvegarde l'état dans le fichier

        Args:
            state: État à sauvegarder

        Returns:
            bool: True si succès, False sinon
        """
        # Écrire de manière atomique (temp + rename)
        temp_file = self.state_file.with_suffix('.tmp')

        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)

            temp_file.replace(self.state_file)
            return True
        except Exception as e:
            print(f"❌ Erreur sauvegarde état: {e}")
            return False

    def _read_sidecar_file(self, filename: str) -> Optional[str]:
        """
        Lit un fichier sidecar

        Args:
            filename: Nom du fichier

        Returns:
            str: Contenu du fichier ou None
        """
        sidecar_path = self.index_dir / filename

        if not sidecar_path.exists():
            return None

        with open(sidecar_path, 'r', encoding='utf-8') as f:
            return f.read().strip()

    def _write_sidecar_file(self, filename: str, content: str) -> bool:
        """
        Écrit dans un fichier sidecar

        Args:
            filename: Nom du fichier
            content: Contenu à écrire

        Returns:
            bool: True si succès, False sinon
        """
        sidecar_path = self.index_dir / filename

        try:
            with open(sidecar_path, 'w', encoding='utf-8') as f:
                f.write(content + '\n')
            return True
        except Exception as e:
            print(f"❌ Erreur écriture sidecar {filename}: {e}")
            return False

    # ============================================================================
    # SNAPSHOT HASH (Sidecar)
    # ============================================================================

    def _read_hash_from_sidecar(self) -> Optional[str]:
        """
        Récupère le dernier hash de snapshot depuis le sidecar

        Returns:
            str: Dernier hash ou None
        """
        return self._read_sidecar_file("last_home_snapshot_hash.txt")

    def _write_hash_to_sidecar(self, hash_value: str) -> bool:
        """
        Écrit le hash dans le sidecar

        Args:
            hash_value: Hash à stocker

        Returns:
            bool: True si succès, False sinon
        """
        return self._write_sidecar_file("last_home_snapshot_hash.txt", hash_value)

    # ============================================================================
    # COOLDOWN & BUDGET CHECKS
    # ============================================================================

    def _now_ts(self) -> float:
        """
        Retourne le timestamp actuel

        Returns:
            float: Timestamp actuel
        """
        return datetime.now(timezone.utc).timestamp()

    def can_poll_home(self, now_ts: Optional[float] = None) -> Tuple[bool, int]:
        """
        Vérifie si le polling home est autorisé

        Args:
            now_ts: Timestamp actuel (optionnel)

        Returns:
            tuple[bool, int]: (can_poll, remaining_seconds)
        """
        state = self._load_state()
        last_poll = state.get("last_home_poll_ts", 0)

        if now_ts is None:
            now_ts = self._now_ts()

        remaining = last_poll + self.HOME_POLL_COOLDOWN - now_ts
        can_poll = remaining <= 0

        if can_poll:
            remaining = 0

        return (can_poll, int(remaining))

    def can_execute_action(self, now_ts: Optional[float] = None) -> Tuple[bool, str]:
        """
        Vérifie si une action peut être exécutée

        Args:
            now_ts: Timestamp actuel (optionnel)

        Returns:
            tuple[bool, str]: (can_execute, reason)
        """
        state = self._load_state()
        last_action = state.get("last_action_ts", 0)

        if now_ts is None:
            now_ts = self._now_ts()

        # Si aucune action n'a été exécutée, autoriser
        if last_action == 0:
            remaining = 0
        else:
            remaining = last_action + self.ACTION_COOLDOWN - now_ts

        # Vérifier le budget journalier
        count = state.get("actions_today_count", 0)
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        state_date = state.get("actions_today_date", "")

        # Reset si nouveau jour
        if state_date != today_str:
            count = 0

        daily_remaining = self.DAILY_ACTION_BUDGET - count

        # Logic: Cooldown blocké si remaining > 0 (temps restant)
        if remaining > 0 and daily_remaining > 0:
            return (False, "cooldown")
        elif remaining > 0 and daily_remaining <= 0:
            return (False, "daily_limit")
        elif remaining <= 0 and daily_remaining <= 0:
            return (False, "both")
        else:
            # remaining <= 0 and daily_remaining > 0: OK pour exécuter
            return (True, None)

    # ============================================================================
    # MARKERS & METRICS
    # ============================================================================

    def mark_home_polled(self, now_ts: Optional[float] = None) -> bool:
        """
        Marque un polling home comme effectué

        Args:
            now_ts: Timestamp actuel (optionnel)

        Returns:
            bool: True si succès, False sinon
        """
        state = self._load_state()

        if now_ts is None:
            now_ts = self._now_ts()

        state["last_home_poll_ts"] = now_ts

        return self._save_state(state)

    def mark_action_executed(self, now_ts: Optional[float] = None) -> bool:
        """
        Marque une action comme exécutée

        Args:
            now_ts: Timestamp actuel (optionnel)

        Returns:
            bool: True si succès, False sinon
        """
        state = self._load_state()

        if now_ts is None:
            now_ts = self._now_ts()

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        state_date = state.get("actions_today_date", "")

        # Reset si nouveau jour
        if state_date != today_str:
            state["actions_today_count"] = 0
            state["actions_today_date"] = today_str

        state["last_action_ts"] = now_ts
        state["actions_today_count"] += 1

        return self._save_state(state)

    def mark_home_poll_skipped(self) -> bool:
        """
        Marque un polling home comme skip

        Returns:
            bool: True si succès, False sinon
        """
        state = self._load_state()
        state["skipped_home_polls"] = state.get("skipped_home_polls", 0) + 1
        return self._save_state(state)

    def mark_action_skipped_cooldown(self, reason: str = "cooldown") -> bool:
        """
        Marque une action comme skip (cooldown)

        Args:
            reason: Raison du skip (cooldown/daily_limit)

        Returns:
            bool: True si succès, False sinon
        """
        state = self._load_state()

        if reason == "cooldown":
            state["skipped_actions_cooldown"] = state.get("skipped_actions_cooldown", 0) + 1
        elif reason == "daily_limit":
            state["skipped_actions_daily_limit"] = state.get("skipped_actions_daily_limit", 0) + 1

        return self._save_state(state)

    # ============================================================================
    # GETTERS
    # ============================================================================

    def get_state(self) -> Dict[str, Any]:
        """
        Retourne l'état actuel (lecture seule)

        Returns:
            dict: État actuel
        """
        return self._load_state()

    def print_state(self):
        """Affiche l'état actuel pour debugging"""
        state = self._load_state()
        now_ts = self._now_ts()

        print("\n" + "=" * 70)
        print("📋 SESSION LIMITS STATE")
        print("=" * 70)

        print(f"\n📊 Daily Budget:")
        count = state.get("actions_today_count", 0)
        budget = self.DAILY_ACTION_BUDGET - count
        print(f"   Actions today: {count}/{self.DAILY_ACTION_BUDGET}")
        print(f"   Remaining: {budget}")

        print(f"\n📸 Last Home Poll:")
        last_poll = state.get("last_home_poll_ts", 0)
        if last_poll > 0:
            elapsed = now_ts - last_poll
            print(f"   Timestamp: {datetime.fromtimestamp(last_poll, tz=timezone.utc).isoformat()}")
            print(f"   Elapsed: {int(elapsed)}s")

        print(f"\n⚡ Last Action:")
        last_action = state.get("last_action_ts", 0)
        if last_action > 0:
            elapsed = now_ts - last_action
            print(f"   Timestamp: {datetime.fromtimestamp(last_action, tz=timezone.utc).isoformat()}")
            print(f"   Elapsed: {int(elapsed)}s")

        print(f"\n📦 Skips:")
        print(f"   Home Polls: {state.get('skipped_home_polls', 0)}")
        print(f"   Actions Cooldown: {state.get('skipped_actions_cooldown', 0)}")
        print(f"   Actions Daily Limit: {state.get('skipped_actions_daily_limit', 0)}")

        print("=" * 70)
