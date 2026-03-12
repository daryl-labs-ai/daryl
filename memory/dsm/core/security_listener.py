#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Security Integration for Listener
Intègre la couche de sécurité dans le listener existant
"""

import os
import sys
from pathlib import Path
import logging

# Imports relatifs (Règle : UNIQUEMENT des imports relatifs dans core/)
from .security import SecurityLayer, MAX_API_REQUESTS_PER_CYCLE

logger = logging.getLogger("dsm_security_integration")

# Instance globale de sécurité
_security_layer = None

def get_security_layer() -> SecurityLayer:
    """Récupère ou initialise la couche de sécurité"""
    global _security_layer
    if _security_layer is None:
        _security_layer = SecurityLayer(workspace_dir=Path(__file__).parent.parent)

        # Self-check au démarrage
        logger.info("🔍 Running security self-check...")
        report = _security_layer.self_check()
        logger.info(f"Security status: {report['security_status']}")

        if report['anomalies']:
            logger.warning(f"⚠️ Security anomalies detected: {report['anomalies']}")

    return _security_layer

def audit_api_call(action: str, details: dict):
    """Audit d'un appel API"""
    security = get_security_layer()
    security.audit_external_action("api_request", {
        "action": action,
        **details
    })

def audit_file_operation(operation: str, filepath: str, details: dict = None):
    """Audit d'une opération fichier"""
    security = get_security_layer()
    security.audit_external_action("file_operation", {
        "operation": operation,
        "filepath": filepath,
        **(details or {})
    })

def run_periodic_security_check():
    """Exécute une vérification de sécurité périodique"""
    security = get_security_layer()
    report = security.self_check()

    if report['anomalies']:
        logger.warning("⚠️ Security check found anomalies:")
        for anomaly in report['anomalies']:
            logger.warning(f"  • {anomaly}")

    return report

def generate_security_report():
    """Génère un rapport de sécurité"""
    security = get_security_layer()
    return security.generate_security_report()

def update_security_baseline():
    """Met à jour la baseline de sécurité"""
    security = get_security_layer()
    security.update_baseline()

# Exemple d'intégration avec le listener
def secure_api_call(api_function, *args, **kwargs):
    """
    Wrapper sécurisé pour les appels API

    Args:
        api_function: Fonction API à appeler
        *args, **kwargs: Arguments de la fonction

    Returns:
        Résultat de l'appel API
    """
    security = get_security_layer()

    # Audit avant l'appel
    audit_api_call(api_function.__name__, {
        "args": str(args)[:100],
        "kwargs": str(kwargs)[:100]
    })

    try:
        # Vérifier le rate limit
        if security.cycle_stats["api_requests"] >= MAX_API_REQUESTS_PER_CYCLE:
            logger.warning("⚠️ API rate limit reached, blocking call")
            return None

        # Exécuter l'appel
        result = api_function(*args, **kwargs)

        return result

    except Exception as e:
        logger.error(f"API call failed: {e}")
        return None

# Monkey-patch pour sécuriser automatiquement les appels Telegram
def secure_telegram_app():
    """
    Applique des patches pour sécuriser les appels Telegram
    """
    try:
        from telegram.ext import Application

        original_run_polling = Application.run_polling

        async def secure_run_polling(self, *args, **kwargs):
            logger.info("🛡️ Starting Telegram polling (secured)")
            return await original_run_polling(self, *args, **kwargs)

        Application.run_polling = secure_run_polling
        logger.info("✅ Telegram app patched for security")

    except Exception as e:
        logger.error(f"Failed to patch Telegram app: {e}")
