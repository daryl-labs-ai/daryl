#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Moltbook Home Normalizer
Extraire les champs stables de /api/v1/home pour le snapshot dedup
"""

import json
import hashlib
from typing import Dict, Any, List
from datetime import datetime


class MoltbookHomeNormalizer:
    """Normalise le payload /api/v1/home pour déduplication"""

    # Champs stables à extraire (indépendants des timestamps/volatile)
    STABLE_FIELDS = {
        "unread_notification_count",
        "unread_message_count",
        "activity_posts_count",
        "following_posts_count",
        "latest_announcement_id"
    }

    def __init__(self, verbose: bool = False):
        """
        Initialise le normalizer

        Args:
            verbose: Afficher les détails du traitement
        """
        self.verbose = verbose
        self.verbose = verbose

    def normalize(self, home: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalise le payload home en ne gardant que les champs stables

        Args:
            home: Payload /api/v1/home brut

        Returns:
            dict: Payload normalisé (stable fields uniquement)
        """
        normalized = {}

        # Extraire les champs de compte
        account = home.get("your_account", {})
        normalized["unread_notification_count"] = account.get("unread_notification_count", 0)

        # Extraire les champs DM
        dms = home.get("your_direct_messages", {})
        unread_dm_str = dms.get("unread_message_count", "0")
        # Gérer "00" comme string
        normalized["unread_message_count"] = int(unread_dm_str) if unread_dm_str.isdigit() else 0

        # Extraire les champs d'activité sur vos posts
        activity = home.get("activity_on_your_posts", [])
        # Extraire uniquement les IDs stables (éviter les timestamps/volatile)
        activity_post_ids = [post.get("post_id") for post in activity]
        normalized["activity_post_ids"] = activity_post_ids
        normalized["activity_posts_count"] = len(activity_post_ids)

        # Extraire les champs des posts suivis
        following = home.get("posts_from_accounts_you_follow", {})
        following_posts = following.get("posts", [])
        # Extraire uniquement les IDs stables
        following_post_ids = [post.get("post_id") for post in following_posts]
        normalized["following_post_ids"] = following_post_ids
        normalized["following_posts_count"] = len(following_post_ids)

        # Extraire l'annonce Moltbook la plus récente
        latest_announcement = home.get("latest_moltbook_announcement", {})
        normalized["latest_announcement_id"] = latest_announcement.get("post_id")

        if self.verbose:
            print(f"📦 Home normalisé :")
            print(f"   🔔 Notifications: {normalized['unread_notification_count']}")
            print(f"   💬 DMs non lus: {normalized['unread_message_count']}")
            print(f"   📊 Activité posts: {normalized['activity_posts_count']}")
            print(f"   👤 Following posts: {normalized['following_posts_count']}")
            print(f"   📢 Dernière annonce: {normalized['latest_announcement_id'][:8] if normalized['latest_announcement_id'] else 'None'}...")

        return normalized

    def compute_hash(self, normalized_home: Dict[str, Any]) -> str:
        """
        Calcule le hash SHA256 du home normalisé

        Args:
            normalized_home: Payload normalisé

        Returns:
            str: Hash SHA256
        """
        # Convertir en JSON avec clés triées (ordre déterministe)
        data_str = json.dumps(normalized_home, sort_keys=True, separators=(',', ':'))

        # Calculer SHA256
        hash_obj = hashlib.sha256(data_str.encode('utf-8'))
        return hash_obj.hexdigest()

    def has_changed(self, normalized_home: Dict[str, Any], last_hash: str) -> bool:
        """
        Vérifie si le home a changé par rapport au dernier hash

        Args:
            normalized_home: Payload normalisé actuel
            last_hash: Dernier hash stocké

        Returns:
            bool: True si le home a changé, False sinon
        """
        current_hash = self.compute_hash(normalized_home)
        return current_hash != last_hash

    def get_metrics(self, normalized_home: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrait les métriques utiles pour la prise de décision

        Args:
            normalized_home: Payload normalisé

        Returns:
            dict: Métriques (notifications, DMs, opportunités)
        """
        # Métriques de base
        metrics = {
            "unread_notifications": normalized_home["unread_notification_count"],
            "unread_dms": normalized_home["unread_message_count"],
            "activity_count": normalized_home["activity_posts_count"],
            "following_count": normalized_home["following_posts_count"]
        }

        # Déduire des opportunités
        # Stratégie simple: prioriser les réponses aux posts avec beaucoup de notifications
        if metrics["unread_notifications"] > 100:
            metrics["high_priority_notifications"] = True

        # Prioriser les DMs non lus
        if metrics["unread_dms"] > 0:
            metrics["unread_dms_priority"] = True

        # Opportunités de commentaire (basé sur l'activité sur vos posts)
        if metrics["activity_count"] > 5:
            metrics["comment_opportunities"] = normalized_home["activity_post_ids"][:3]

        return metrics
