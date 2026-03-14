# Intégration DSM dans le runtime Clawdbot

## Fichiers concernés (côté Clawdbot)

- **`/home/buraluxtr/clawd/dsm_logger.py`** — Middleware DSM (fail-safe), écrit dans le shard **clawdbot_sessions**.
- **`/home/buraluxtr/clawd/dsm_bot.py`** — Appelle le middleware au démarrage, sur action, et à l’arrêt.
- **`/home/buraluxtr/clawd/dsm_analytics.py`** — Script minimal : lit clawdbot_sessions, comptes par action, affiche les actions les plus fréquentes.

## Shard dédié : clawdbot_sessions

Les événements Clawdbot sont écrits dans le shard **clawdbot_sessions** (et non plus `sessions`). Chaque entrée a :

- **source** = `"clawdbot"`
- **metadata** : `event_type` (session_start | tool_call | session_end), `action_name` (pour tool_call), `timestamp` (ISO), `error` (bool, optionnel pour DSM-ANS).

## Comportement

1. **Au démarrage** : `dsm_logger.init(data_dir)` crée un `Storage` ; puis `start_session("clawdbot")` écrit un événement session_start dans clawdbot_sessions. `atexit.register(dsm_logger.end_session)` enregistre la fin de session à la sortie du processus.
2. **Sur action** : `dsm_logger.log_action(action_name, payload, error=False)` écrit un tool_call avec action_name, timestamp, error dans les metadata.
3. **À l’arrêt** : `end_session()` écrit session_end puis ferme la session.

Si `dsm_v2` est absent ou qu’une erreur DSM se produit, le middleware ne lève pas d’exception (fail-safe).

## DSM-ANS

Les champs **action_name**, **source**, **timestamp** et **error** dans les metadata sont compatibles avec une exploitation ultérieure par les modules **dsm_v2.ans** (analytics / recommandations). Aucune modification des fichiers du noyau DSM (memory/dsm/core).

## Vérifier les sessions

```bash
dsm read clawdbot_sessions --data-dir /home/buraluxtr/clawd/data --limit 20
```

## Analytics

```bash
cd /home/buraluxtr/clawd
PYTHONPATH=/opt/daryl python3 dsm_analytics.py [--limit 500] [--data-dir /home/buraluxtr/clawd/data]
```

Affiche : nombre d’entrées lues, session starts/ends, comptages par action (les plus fréquentes en premier).

## Dépendance

Le runtime Clawdbot doit avoir accès au package `dsm_v2` (par ex. `PYTHONPATH=/opt/daryl` ou `pip install -e /opt/daryl`).
