"""
retrain_push.py — Standalone ML Training Script
=================================================
Run by GitHub Actions every 12 hours (or manually anytime).
Fetches maximum Jira data, trains model, pushes to MongoDB.

Also works locally:
  python retrain_push.py

Env vars required (set in GitHub Secrets or local .env):
  JIRA_CLOUD_ID, JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN
  JIRA_PROJECT, MONGODB_URI, MONGODB_DB (optional, default: jira_dashboard)
"""
import os, sys, json, time, logging
from datetime import datetime

# ── Load .env if running locally ──────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

RESULT_PATH = os.getenv("RESULT_PATH", "/tmp/retrain_result.json")


def check_env():
    """Verify all required env vars are present."""
    required = ["JIRA_CLOUD_ID", "JIRA_EMAIL", "JIRA_API_TOKEN", "MONGODB_URI"]
    missing  = [k for k in required if not os.getenv(k)]
    if missing:
        log.error(f"Missing env vars: {missing}")
        log.error("Set them in GitHub Secrets or your local .env file")
        sys.exit(1)
    log.info("✓ All required env vars present")


def run():
    start = time.time()
    log.info("=" * 60)
    log.info("ML RETRAIN & PUSH — START")
    log.info(f"MAX_ISSUES : {os.getenv('MAX_ISSUES', '2000')}")
    log.info(f"DAYS_BACK  : {os.getenv('DAYS_BACK',  '730')}")
    log.info(f"MONGODB_DB : {os.getenv('MONGODB_DB', 'jira_dashboard')}")
    log.info("=" * 60)

    check_env()

    # ── Step 1: Fetch issues from Jira ────────────────────────────────────────
    log.info("Step 1/4 — Fetching issues from Jira...")
    try:
        import data as D
        issues = D.get_issues(force=True)
        if not issues:
            raise ValueError("No issues returned from Jira")
        log.info(f"  ✓ Fetched {len(issues)} issues")
    except Exception as e:
        log.error(f"  ✗ Jira fetch failed: {e}")
        _save_result({"status": "failed", "stage": "fetch", "error": str(e)})
        sys.exit(1)

    # ── Step 2: Run MLOps pipeline ────────────────────────────────────────────
    log.info("Step 2/4 — Running MLOps pipeline (engineer → split → train)...")
    try:
        import mlops
        result = mlops.run_pipeline(
            issues=issues,
            config={
                "model_type":    "random_forest",
                "n_estimators":  300,
                "max_depth":     None,
                "n_clusters":    3,
                "contamination": 0.1,
                "test_size":     0.2,
            }
        )
        if "error" in result:
            raise ValueError(result["error"])
        log.info(f"  ✓ Training complete")
        log.info(f"    AUC (test) : {result.get('auc_test', '—')}")
        log.info(f"    F1  (test) : {result.get('f1_test',  '—')}")
        log.info(f"    Train n    : {result.get('n_train',  '—')}")
        log.info(f"    Slip rate  : {result.get('slip_rate','—')}%")
        if result.get("warning"):
            log.warning(f"  ⚠ {result['warning']}")
    except Exception as e:
        log.error(f"  ✗ Pipeline failed: {e}")
        _save_result({"status": "failed", "stage": "train", "error": str(e)})
        sys.exit(1)

    # ── Step 3: Verify model is in MongoDB ────────────────────────────────────
    log.info("Step 3/4 — Verifying model in MongoDB...")
    try:
        bundle, run_doc = mlops.load_model_from_mongo()
        if bundle:
            log.info(f"  ✓ Model confirmed in MongoDB")
            log.info(f"    Version : {run_doc.get('version', '—')}")
            log.info(f"    AUC     : {run_doc.get('auc_test', '—')}")
        else:
            log.warning("  ⚠ Model not found in MongoDB — may have been saved locally only")
            log.warning("    Check that MONGODB_URI is set correctly")
    except Exception as e:
        log.warning(f"  ⚠ MongoDB verification failed: {e}")

    # ── Step 4: Save result summary ───────────────────────────────────────────
    elapsed = round(time.time() - start, 1)
    summary = {
        "status":       "success" if "error" not in result else "warning",
        "timestamp":    datetime.utcnow().isoformat(),
        "elapsed_sec":  elapsed,
        "issues_used":  len(issues),
        **{k: result.get(k) for k in
           ["auc_test","f1_test","n_train","slip_rate","version","auc_cv_mean"]},
    }
    _save_result(summary)

    log.info("=" * 60)
    log.info(f"✓ DONE in {elapsed}s")
    log.info(f"  Render will use this model on next prediction call")
    log.info("=" * 60)


def _save_result(data):
    try:
        os.makedirs(os.path.dirname(RESULT_PATH), exist_ok=True)
        with open(RESULT_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)
        log.info(f"Result saved to {RESULT_PATH}")
    except Exception as e:
        log.warning(f"Could not save result file: {e}")


if __name__ == "__main__":
    run()
