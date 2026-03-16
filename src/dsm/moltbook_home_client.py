#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Moltbook Home Client
Client pour /api/v1/home - le nouveau endpoint unifié Moltbook
"""

import hashlib
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import subprocess


class MoltbookHomeClient:
    """Client Moltbook Home endpoint"""

    def __init__(self, api_key: str, base_url: str = "https://moltbook.com/api/v1"):
        """
        Initialise le client Home

        Args:
            api_key: Clé API Moltbook
            base_url: URL de base de l'API Moltbook
        """
        self.api_key = api_key
        self.base_url = base_url
        self.cache = {}
        self.cache_ttl = 30  # Secondes (API cache de 30s)

    def _run_curl(self, endpoint: str) -> Optional[Dict]:
        """
        Exécute une requête via curl

        Args:
            endpoint: Endpoint à appeler

        Returns:
            dict: Réponse JSON ou None si erreur
        """
        url = f"{self.base_url}/{endpoint}"
        cmd = [
            "curl", "-s", "--max-time", "10",
            "-H", f"Authorization: Bearer {self.api_key}",
            url
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )

            if result.returncode == 0 and result.stdout:
                return json.loads(result.stdout)
            else:
                print(f"❌ Erreur curl: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            print(f"❌ Timeout: {endpoint}")
            return None
        except json.JSONDecodeError as e:
            print(f"❌ Erreur JSON: {e}")
            return None

    def fetch_home(self, use_cache: bool = True) -> Optional[Dict]:
        """
        Récupère le snapshot home complet

        Args:
            use_cache: Utiliser le cache si disponible

        Returns:
            dict: Snapshot home ou None si erreur
        """
        # Vérifier le cache
        if use_cache:
            cached = self._get_cached("home")
            if cached:
                print("📦 Home depuis cache")
                return cached

        # Appel API
        print("📸 Récupération snapshot home...")
        data = self._run_curl("home")

        # L'endpoint /home retourne les données directement
        if data and isinstance(data, dict):
            # Vérifier si c'est une réponse d'erreur
            if data.get("status") == "error":
                print(f"❌ Erreur API: {data}")
                return None

            # Mettre en cache
            self._set_cached("home", data)

            return data
        else:
            print(f"❌ Erreur fetch_home: {data}")
            return None

    def compute_hash(self, home: Dict) -> str:
        """
        Calcule le hash d'un snapshot home

        Args:
            home: Snapshot home

        Returns:
            str: Hash SHA256
        """
        # Exclure les champs volatils (timestamps, random)
        stable_data = {
            "unread_notification_count": home.get("your_account", {}).get("unread_notification_count", 0),
            "unread_message_count": home.get("your_direct_messages", {}).get("unread_message_count", 0),
            "activity_posts": len(home.get("activity_on_your_posts", [])),
            "following_posts": len(home.get("posts_from_accounts_you_follow", {}).get("posts", []))
        }

        data_str = json.dumps(stable_data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    def get_notifications_count(self, home: Dict) -> int:
        """
        Récupère le nombre de notifications

        Args:
            home: Snapshot home

        Returns:
            int: Nombre de notifications
        """
        account = home.get("your_account", {})
        return account.get("unread_notification_count", 0)

    def get_unread_dms(self, home: Dict) -> int:
        """
        Récupère le nombre de DMs non lus

        Args:
            home: Snapshot home

        Returns:
            int: Nombre de DMs non lus
        """
        dms = home.get("your_direct_messages", {})
        # Unread count peut être "00" comme string
        unread = dms.get("unread_message_count", "0")
        if isinstance(unread, str):
            # Extraire le chiffre
            unread = int(unread) if unread.isdigit() else 0
        return unread

    def get_activity_on_posts(self, home: Dict) -> list:
        """
        Récupère l'activité sur vos posts

        Args:
            home: Snapshot home

        Returns:
            list: Liste des activités sur posts
        """
        return home.get("activity_on_your_posts", [])

    def get_high_karma_opportunities(self, home: Dict, min_karma: int = 500) -> list:
        """
        Identifie les opportunités de haut karma dans le feed suivi

        Args:
            home: Snapshot home
            min_karma: Karma minimum pour être considéré "haut karma"

        Returns:
            list: Liste d'opportunités
        """
        follow_feed = home.get("posts_from_accounts_you_follow", {})
        posts = follow_feed.get("posts", [])
        opportunities = []

        for post in posts:
            # Créer un objet post avec author karma (dummy, car pas dans le feed)
            # En pratique, il faudrait faire un appel API pour chaque post
            # Pour l'instant, on se base sur les upvotes
            upvotes = post.get("upvotes", 0)

            if upvotes >= 10:  # Opportunité basée sur upvotes au lieu de karma
                opportunities.append({
                    "post_id": post.get("post_id"),
                    "title": post.get("title", ""),
                    "upvotes": upvotes,
                    "comment_count": post.get("comment_count", 0),
                    "submolt": post.get("submolt_name", "")
                })

        return opportunities

    def get_suggested_actions(self, home: Dict) -> list:
        """
        Récupère les actions suggérées par Moltbook

        Args:
            home: Snapshot home

        Returns:
            list: Liste d'actions suggérées
        """
        return home.get("what_to_do_next", [])

    # ========================================================================
    # INTERNAL HELPERS
    # ========================================================================

    def _get_cached(self, key: str) -> Optional[Dict]:
        """Récupère une valeur du cache"""
        if key in self.cache:
            cached_data, cached_time = self.cache[key]
            age = (datetime.now(timezone.utc) - cached_time).total_seconds()

            if age < self.cache_ttl:
                return cached_data

        return None

    def _set_cached(self, key: str, data: Dict):
        """Met en cache une valeur"""
        self.cache[key] = (data, datetime.now(timezone.utc))
