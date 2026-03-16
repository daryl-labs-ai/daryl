#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSM v2 - Stability Validation Suite
Master runner for all DSM v2 stability tests
"""

import sys
import subprocess
import json
import time
from pathlib import Path
from datetime import datetime, timezone

# Ajouter le parent au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_test(script_name: str, script_path: Path, description: str) -> dict:
    """Exécute un test et retourne les résultats"""

    print("\n" + "=" * 70)
    print(f"🚀 RUNNING TEST: {script_name}")
    print("=" * 70)
    print(f"Description: {description}")
    print(f"Script: {script_path.name}")
    print("=" * 70 + "\n")

    start_time = time.time()
    
    try:
        result = subprocess.run(
            ["python3", str(script_path)],
            cwd=str(script_path.parent),
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes max par test
        )
        
        elapsed_time = time.time() - start_time
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
        
        # Analyser la sortie
        success = exit_code == 0
        
        # Extraire le rapport JSONL du stdout
        report_lines = []
        for line in stdout.split('\n'):
            if line.strip():
                # Tenter de parser comme JSON
                try:
                    report_data = json.loads(line.strip())
                    report_lines.append(report_data)
                except:
                    # Pas du JSON, ignorer
                    pass
        
        # Trouver le rapport final
        final_report = None
        for line in reversed(report_lines):
            if isinstance(line, dict) and "test_status" in line:
                final_report = line
                break
        
        return {
            "test_name": script_name,
            "script": script_path.name,
            "description": description,
            "success": success,
            "exit_code": exit_code,
            "elapsed_time": elapsed_time,
            "stdout": stdout,
            "stderr": stderr,
            "report": final_report
        }
        
    except subprocess.TimeoutExpired:
        elapsed_time = time.time() - start_time
        print(f"\n❌ ERREUR: Test dépassé le délai de 600s")
        
        return {
            "test_name": script_name,
            "script": script_path.name,
            "description": description,
            "success": False,
            "exit_code": -1,
            "elapsed_time": elapsed_time,
            "stdout": "",
            "stderr": "TIMEOUT",
            "report": None
        }
    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"\n❌ ERREUR: Exception lors de l'exécution du test: {e}")
        
        return {
            "test_name": script_name,
            "script": script_path.name,
            "description": description,
            "success": False,
            "exit_code": -2,
            "elapsed_time": elapsed_time,
            "stdout": "",
            "stderr": str(e),
            "report": None
        }


def run_all_tests():
    """Exécute tous les tests de stabilité"""

    print("=" * 70)
    print("🧪 DSM v2 - STABILITY VALIDATION SUITE")
    print("=" * 70)
    print("\nRunning complete stability validation on DSM v2...")
    print("Environment: Production VM")
    print("Workspace: /home/buraluxtr/clawd/")
    print("Constraints:")
    print("- Do NOT modify architecture")
    print("- Do NOT delete any data")
    print("- Do NOT reset shards")
    print("- Do NOT modify limits configuration")
    print("- Only run controlled validation tests")
    print("=" * 70 + "\n")

    test_dir = Path(__file__).parent.parent / "tests"
    
    # Configuration des tests
    tests = [
        {
            "name": "STRESS_TEST",
            "script": test_dir / "test_stress_1000.py",
            "description": "Validate shard rotation and hash chain stability (1000 events)"
        },
        {
            "name": "CRASH_RECOVERY_TEST",
            "script": test_dir / "test_crash_recovery.py",
            "description": "Verify append-only resilience with simulated crash"
        },
        {
            "name": "LIMITS_MULTI_SESSION_TEST",
            "script": test_dir / "test_limits_multi_session.py",
            "description": "Validate cooldowns and budgets across multiple sessions"
        }
    ]
    
    # ============================================================================
    # EXÉCUTION DES TESTS
    # ============================================================================
    all_results = []
    
    for test in tests:
        if not test["script"].exists():
            print(f"⚠️  Script introuvable: {test['script']}")
            all_results.append({
                "test_name": test["name"],
                "script": test["script"].name,
                "success": False,
                "error": "Script introuvable"
            })
            continue
        
        result = run_test(
            script_name=test["name"],
            script_path=test["script"],
            description=test["description"]
        )
        
        all_results.append(result)
        
        # Afficher le statut du test
        status_icon = "✅" if result["success"] else "❌"
        print(f"\n{status_icon} {result['test_name']}: {result['elapsed_time']:.2f}s")
        
        if result["success"] and result["report"]:
            print(f"   Report: {result['report']}")
        elif not result["success"]:
            print(f"   Erreur: {result['stderr'][:100]}...")
    
    # ============================================================================
    # TRACE REPLAY TEST
    # ============================================================================
    print("\n" + "=" * 70)
    print("🧪 TRACE REPLAY TEST")
    print("=" * 70)
    print("Note: Trace replay test requires a session ID from previous tests")
    print("Skipping automatic trace replay in suite. Run manually:")
    print("  python3 scripts/trace_replay.py --list-sessions")
    print("  python3 scripts/trace_replay.py --session <session_id>")
    print("=" * 70 + "\n")
    
    # ============================================================================
    # RAPPORT FINAL
    # ============================================================================
    print("\n" + "=" * 70)
    print("📋 DSM V2 STABILITY VALIDATION REPORT")
    print("=" * 70)
    print(f"\nTimestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Tests exécutés: {len(all_results)}")
    
    # Tableau de synthèse
    print(f"\n{'Test':<30} {'Status':<10} {'Time':<10} {'Details'}")
    print("-" * 70)
    
    for result in all_results:
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        time_str = f"{result['elapsed_time']:.1f}s"
        
        # Extraire les détails du rapport
        if result["report"]:
            details = json.dumps(result["report"])
        else:
            details = result["stderr"][:50] if result["stderr"] else "N/A"
        
        print(f"{result['test_name']:<30} {status:<10} {time_str:<10} {details}")
    
    # Analyse globale
    print("\n" + "=" * 70)
    print("📊 ANALYSE GLOBALE")
    print("=" * 70)
    
    passed_tests = [r for r in all_results if r["success"]]
    failed_tests = [r for r in all_results if not r["success"]]
    
    print(f"\n✅ Tests passés: {len(passed_tests)}/{len(all_results)}")
    print(f"❌ Tests échoués: {len(failed_tests)}/{len(all_results)}")
    
    if failed_tests:
        print("\n⚠️  Tests échoués:")
        for result in failed_tests:
            print(f"   - {result['test_name']}: {result['stderr'][:80]}")
    
    # Calcul du score de stabilité DSM v2
    stability_score = 0
    total_weight = 0
    
    if passed_tests:
        # Stress test (poids: 40)
        if passed_tests[0]["report"]:
            if passed_tests[0]["report"].get("hash_chain_status") == "VALID":
                stability_score += 40
                total_weight += 40
            else:
                total_weight += 40
        
        # Crash recovery test (poids: 30)
        if len(passed_tests) > 1 and passed_tests[1]["report"]:
            if passed_tests[1]["report"].get("recovery_status") == "SUCCESS":
                stability_score += 30
                total_weight += 30
            else:
                total_weight += 30
        
        # Limits manager test (poids: 30)
        if len(passed_tests) > 2 and passed_tests[2]["report"]:
            if passed_tests[2]["report"].get("test_status") == "PASSED":
                stability_score += 30
                total_weight += 30
            else:
                total_weight += 30
    
    # Score final (0-100)
    final_score = int((stability_score / total_weight) * 100) if total_weight > 0 else 0
    
    print(f"\n📊 DSM v2 Stability Score: {final_score}/100")
    
    # Verdict de production
    if final_score >= 90:
        verdict = "🟢 PRODUCTION READY"
        print("\n🎉 VERDICT: PRODUCTION READY")
        print("   DSM v2 is stable and ready for production use")
        production_ready = True
    elif final_score >= 70:
        verdict = "🟡 MOSTLY STABLE"
        print("\n⚠️  VERDICT: MOSTLY STABLE")
        print("   DSM v2 is mostly stable with minor issues")
        production_ready = False
    elif final_score >= 50:
        verdict = "🟠 NEEDS FIXES"
        print("\n⚠️  VERDICT: NEEDS FIXES")
        print("   DSM v2 has stability issues that should be addressed")
        production_ready = False
    else:
        verdict = "🔴 UNSTABLE"
        print("\n❌ VERDICT: UNSTABLE")
        print("   DSM v2 is not ready for production use")
        production_ready = False
    
    # Rapport final JSON
    final_report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tests_executed": len(all_results),
        "tests_passed": len(passed_tests),
        "tests_failed": len(failed_tests),
        "stability_score": final_score,
        "production_ready": production_ready,
        "verdict": verdict,
        "test_results": all_results
    }
    
    print("\n" + "=" * 70)
    print("📋 RAPPORT FINAL (JSON)")
    print("=" * 70)
    print(json.dumps(final_report, indent=2))
    
    # Sauvegarder le rapport
    report_path = Path(__file__).parent / "dsm_stability_report.json"
    report_path.write_text(json.dumps(final_report, indent=2))
    print(f"\n✅ Rapport sauvegardé: {report_path}")
    
    return final_report


if __name__ == "__main__":
    final_report = run_all_tests()
    
    print("\n" + "=" * 70)
    print("🧪 STABILITY VALIDATION COMPLETE")
    print("=" * 70)
    print(f"Final Status: {final_report['verdict']}")
    print(f"Stability Score: {final_report['stability_score']}/100")
    print(f"Production Ready: {'Yes' if final_report['production_ready'] else 'No'}")
    print("=" * 70)
