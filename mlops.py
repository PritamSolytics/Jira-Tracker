"""
mlops.py — MLOps Pipeline Orchestrator
=======================================
Stages:
  1. Ingest   — fetch from Jira, save raw to MongoDB
  2. Process  — parse + clean, save processed to MongoDB
  3. Engineer — build features, save feature dataset to MongoDB
  4. Split    — stratified train/test split, save split metadata
  5. Train    — fit model + preprocessor, evaluate, save to MongoDB (GridFS)
  6. Register — log run metadata, auto-rollback if worse than previous
  7. Predict  — load latest model from MongoDB, run inference on open issues

Run locally:
  python mlops.py --run pipeline   (full pipeline)
  python mlops.py --run predict    (inference only)
  python mlops.py --run status     (show model registry)
"""
import os, json, logging, warnings, io, gc
from datetime import datetime, date
warnings.filterwarnings("ignore")

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import numpy as np
import pandas as pd
import joblib

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MONGODB_URI = os.getenv("MONGODB_URI", "")
DB_NAME     = os.getenv("MONGODB_DB", "jira_dashboard")


# ── MongoDB helpers ────────────────────────────────────────────────────────────
def _db():
    from pymongo import MongoClient
    return MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)[DB_NAME]

def _gridfs():
    import gridfs
    return gridfs.GridFS(_db())

def _mongo_available():
    if not MONGODB_URI: return False
    try: _db().command("ping"); return True
    except: return False


# ── Stage 1: Ingest ───────────────────────────────────────────────────────────
def ingest(issues_raw):
    """Save raw Jira issue list to MongoDB."""
    if not _mongo_available():
        log.warning("MongoDB unavailable — skipping raw save")
        return
    db = _db()
    ts = datetime.utcnow().isoformat()
    doc = {"timestamp": ts, "count": len(issues_raw), "issues": issues_raw}
    db["jira_raw"].insert_one(doc)
    # Keep only last 5 raw snapshots
    all_ids = [d["_id"] for d in db["jira_raw"].find({}, {"_id":1}).sort("timestamp",-1)]
    if len(all_ids) > 5:
        db["jira_raw"].delete_many({"_id": {"$in": all_ids[5:]}})
    log.info(f"Ingest: saved {len(issues_raw)} raw issues")


# ── Stage 2: Process ──────────────────────────────────────────────────────────
def save_processed(issues):
    """Save parsed issue dicts to MongoDB."""
    if not _mongo_available(): return
    db = _db()
    ts = datetime.utcnow().isoformat()
    # Strip non-serializable types
    clean = [{k: (v if not isinstance(v, date) else str(v)) for k,v in i.items()} for i in issues]
    db["jira_processed"].replace_one({"_id":"latest"}, {"_id":"latest","timestamp":ts,"issues":clean}, upsert=True)
    log.info(f"Process: saved {len(clean)} processed issues")


def load_processed():
    """Load latest processed issues from MongoDB."""
    if not _mongo_available(): return None
    doc = _db()["jira_processed"].find_one({"_id":"latest"})
    return doc["issues"] if doc else None


# ── Stage 3: Engineer ─────────────────────────────────────────────────────────
def save_features(df, version=None):
    """Save feature-engineered DataFrame to MongoDB."""
    if not _mongo_available(): return
    db = _db()
    ts = datetime.utcnow().isoformat()
    version = version or ts[:16]
    doc = {
        "_id": "latest",
        "timestamp": ts,
        "version": version,
        "shape": list(df.shape),
        "columns": list(df.columns),
        "records": df.to_dict("records"),
    }
    db["jira_features"].replace_one({"_id":"latest"}, doc, upsert=True)
    log.info(f"Engineer: saved features {df.shape}")


def load_features():
    """Load latest feature dataset from MongoDB as DataFrame."""
    if not _mongo_available(): return None
    doc = _db()["jira_features"].find_one({"_id":"latest"})
    if not doc: return None
    return pd.DataFrame(doc["records"])


# ── Stage 4: Split ────────────────────────────────────────────────────────────
def stratified_split(df, features, target_col="closed_on_time", test_size=0.2):
    """
    Stratified train/test split on labeled data.
    Returns X_train, X_test, y_train, y_test, split_meta.
    """
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    labeled = df[df[target_col].notna()].copy()
    if len(labeled) < 20:
        raise ValueError(f"Need >= 20 labeled samples, got {len(labeled)}")

    X = labeled[features].fillna(0)
    y = labeled[target_col].astype(int)

    # Fit scaler on ALL data (labeled + unlabeled) for better representation
    scaler = StandardScaler()
    scaler.fit(df[features].fillna(0))
    X_scaled = scaler.transform(X)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X_scaled, y, test_size=test_size, random_state=42, stratify=y
    )

    split_meta = {
        "total_labeled": len(labeled),
        "n_train": len(X_tr),
        "n_test":  len(X_te),
        "slip_rate_train": round(float(y_tr.mean()) * 100, 1),
        "slip_rate_test":  round(float(y_te.mean()) * 100, 1),
        "features_used": features,
        "test_size": test_size,
    }
    log.info(f"Split: {len(X_tr)} train / {len(X_te)} test | slip rate {split_meta['slip_rate_train']}%")
    return X_tr, X_te, y_tr, y_te, scaler, split_meta


# ── Stage 5: Train ────────────────────────────────────────────────────────────
def train(X_tr, X_te, y_tr, y_te, scaler, split_meta, config=None):
    """
    Train slip predictor, K-Means clustering, Isolation Forest.
    Returns trained models + evaluation metrics.
    """
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, IsolationForest
    from sklearn.linear_model import LogisticRegression
    from sklearn.cluster import KMeans
    from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score
    from sklearn.model_selection import StratifiedKFold, cross_val_score

    cfg = {"model_type":"random_forest","n_estimators":200,"max_depth":None,
           "n_clusters":3,"contamination":0.1}
    if config: cfg.update({k:v for k,v in config.items() if v is not None})

    # ── Slip predictor ────────────────────────────────────────────────────────
    if cfg["model_type"] == "gradient_boosting":
        clf = GradientBoostingClassifier(n_estimators=cfg["n_estimators"],
                                          max_depth=cfg["max_depth"] or 4, random_state=42)
    elif cfg["model_type"] == "logistic":
        clf = LogisticRegression(max_iter=500, class_weight="balanced", random_state=42)
    else:
        clf = RandomForestClassifier(n_estimators=cfg["n_estimators"], max_depth=cfg["max_depth"],
                                      class_weight="balanced", random_state=42, n_jobs=-1)
    clf.fit(X_tr, y_tr)
    # [:,1] = probability of on-time (positive class)
    y_prob = clf.predict_proba(X_te)[:,1]
    y_pred = clf.predict(X_te)

    # Cross-val
    cv = StratifiedKFold(n_splits=min(5, len(y_tr)//5 or 2), shuffle=True, random_state=42)
    cv_scores = cross_val_score(clf, X_tr, y_tr, cv=cv, scoring="roc_auc")

    metrics = {
        "auc_test":   round(float(roc_auc_score(y_te, y_prob)), 4),
        "f1_test":    round(float(f1_score(y_te, y_pred, zero_division=0)), 4),
        "precision":  round(float(precision_score(y_te, y_pred, zero_division=0)), 4),
        "recall":     round(float(recall_score(y_te, y_pred, zero_division=0)), 4),
        "cv_auc_mean":round(float(cv_scores.mean()), 4),
        "cv_auc_std": round(float(cv_scores.std()), 4),
    }

    # Feature importance
    feat_imp = {}
    if hasattr(clf, "feature_importances_"):
        feat_imp = dict(zip(split_meta["features_used"],
                            [round(float(x),4) for x in clf.feature_importances_]))

    # ── K-Means clustering ────────────────────────────────────────────────────
    X_all_scaled = np.vstack([X_tr, X_te])
    km = KMeans(n_clusters=cfg["n_clusters"], random_state=42, n_init=10)
    km.fit(X_all_scaled)

    # Auto-label clusters by mean delivery_risk_signal
    y_all = np.concatenate([y_tr, y_te])
    cluster_risk = {}
    for c in range(cfg["n_clusters"]):
        mask = km.labels_ == c
        cluster_risk[c] = float(y_all[mask].mean()) if mask.sum() > 0 else 0.5
    sorted_clusters = sorted(cluster_risk, key=cluster_risk.get, reverse=True)
    labels = ["Critical","Elevated","Standard"] + [f"Cluster {i}" for i in range(3, cfg["n_clusters"])]
    cluster_labels = {str(c): labels[i] for i,c in enumerate(sorted_clusters)}

    # ── Isolation Forest ──────────────────────────────────────────────────────
    iso = IsolationForest(contamination=cfg["contamination"], random_state=42, n_jobs=-1)
    iso.fit(X_all_scaled)

    return {
        "clf": clf, "km": km, "iso": iso, "scaler": scaler,
        "metrics": metrics, "feat_imp": feat_imp,
        "cluster_labels": cluster_labels, "config": cfg,
    }


# ── Stage 6: Save & Register ──────────────────────────────────────────────────
def save_model_to_mongo(trained, split_meta, version=None):
    """
    Serialize and save model bundle to MongoDB GridFS.
    Auto-rollback: if new AUC < previous AUC - 0.02, keep old model.
    """
    if not _mongo_available():
        log.warning("MongoDB unavailable — saving to local disk only")
        _save_local(trained, split_meta)
        return None

    db = _db()
    fs = _gridfs()
    ts = datetime.utcnow().isoformat()
    version = version or ts[:16].replace("T","_").replace(":","")

    # Check rollback condition
    prev = db["ml_runs"].find_one({"status":"active"})
    new_auc = trained["metrics"]["auc_test"]
    if prev and prev.get("auc_test",0) - new_auc > 0.02:
        log.warning(f"New AUC {new_auc} is worse than previous {prev['auc_test']} — keeping old model")
        db["ml_runs"].insert_one({
            "version":version,"timestamp":ts,"status":"rejected_rollback",
            **trained["metrics"], **split_meta, "config":trained["config"],
        })
        return "rollback"

    # Serialize bundle
    bundle = {
        "clf":    trained["clf"],
        "km":     trained["km"],
        "iso":    trained["iso"],
        "scaler": trained["scaler"],
    }
    buf = io.BytesIO()
    joblib.dump(bundle, buf)
    buf.seek(0)

    # Remove old GridFS files
    for f in fs.find({"filename":"ml_bundle"}): fs.delete(f._id)

    # Save new
    file_id = fs.put(buf.read(), filename="ml_bundle", version=version)

    # Deactivate previous runs
    db["ml_runs"].update_many({"status":"active"}, {"$set":{"status":"archived"}})

    # Log this run
    run_doc = {
        "version":          version,
        "timestamp":        ts,
        "status":           "active",
        "gridfs_id":        str(file_id),
        "features_used":    split_meta["features_used"],
        "cluster_labels":   trained["cluster_labels"],
        "feat_importance":  trained["feat_imp"],
        "config":           trained["config"],
        **trained["metrics"],
        **{k:v for k,v in split_meta.items() if k != "features_used"},
    }
    db["ml_runs"].insert_one(run_doc)
    log.info(f"Model saved: version={version} AUC={new_auc} GridFS_id={file_id}")

    # Also save local backup
    _save_local(trained, split_meta)
    return version


def _save_local(trained, split_meta=None):
    """Local disk backup."""
    import os
    MODEL_DIR = os.getenv("MODEL_DIR", os.path.join(os.getenv("DATA_DIR","data"),"models"))
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(trained["clf"],    os.path.join(MODEL_DIR,"slip_predictor.pkl"))
    joblib.dump(trained["km"],     os.path.join(MODEL_DIR,"kmeans.pkl"))
    joblib.dump(trained["iso"],    os.path.join(MODEL_DIR,"isolation_forest.pkl"))
    joblib.dump(trained["scaler"], os.path.join(MODEL_DIR,"scaler.pkl"))
    import json
    meta = {
        "trained_at":       datetime.utcnow().isoformat(),
        "features_used":    list(trained["feat_imp"].keys()) if trained["feat_imp"] else [],
        "feature_importance": trained["feat_imp"],
        "cluster_labels":   trained["cluster_labels"],
        "model_type":       trained["config"].get("model_type", "random_forest"),
        "config":           trained["config"],
        "contamination":    trained["config"].get("contamination", 0.1),
        # split metadata
        "n_train":          split_meta["n_train"]          if split_meta else None,
        "n_test":           split_meta["n_test"]           if split_meta else None,
        "slip_rate":        split_meta["slip_rate_train"]  if split_meta else None,
        # all metrics: auc_test, f1_test, precision, recall, cv_auc_mean, cv_auc_std
        **trained["metrics"],
    }
    with open(os.path.join(MODEL_DIR,"meta.json"),"w") as f: json.dump(meta,f,indent=2)


# ── Stage 7: Load model ───────────────────────────────────────────────────────
def load_model_from_mongo():
    """Load latest active model bundle from MongoDB GridFS."""
    if not _mongo_available(): return None, None
    db = _db()
    fs = _gridfs()
    run = db["ml_runs"].find_one({"status":"active"})
    if not run: return None, None
    try:
        gf = fs.find_one({"filename":"ml_bundle"})
        if not gf: return None, None
        bundle = joblib.load(io.BytesIO(gf.read()))
        return bundle, run
    except Exception as e:
        log.error(f"Model load failed: {e}")
        return None, None


def get_model_registry():
    """Return list of all training runs for UI display."""
    if not _mongo_available(): return []
    runs = list(_db()["ml_runs"].find({},{"_id":0,"gridfs_id":0}).sort("timestamp",-1).limit(10))
    return runs


# ── Full Pipeline ─────────────────────────────────────────────────────────────
def run_pipeline(issues=None, config=None):
    """
    Run full MLOps pipeline.
    Call this locally or from the dashboard (PM only).
    """
    import ml_engine as ME
    import data as D

    log.info("=== MLOps Pipeline Start ===")

    # Stage 1: Ingest
    if issues is None:
        issues = D.get_issues(force=True)
    log.info(f"Stage 1 Ingest: {len(issues)} issues")

    # Stage 2: Process — save parsed issues
    save_processed(issues)

    # Stage 3: Engineer
    log.info("Stage 3 Engineer: building features...")
    df = ME.engineer_features(issues)
    save_features(df)
    log.info(f"  Features shape: {df.shape}")

    # Feature drift detection vs last training
    drift = detect_feature_drift(df)
    if drift:
        log.warning(f"Feature drift detected: {drift}")

    # Stage 4: Split
    features = [f for f in ME.ALL_FEATURES if f in df.columns]
    cfg = {"model_type":"random_forest","n_estimators":200,"max_depth":None,
           "n_clusters":3,"contamination":0.1,"test_size":0.2}
    if config: cfg.update(config)

    try:
        X_tr, X_te, y_tr, y_te, scaler, split_meta = stratified_split(
            df, features, test_size=cfg["test_size"]
        )
    except ValueError as e:
        log.error(f"Split failed: {e}")
        return {"error": str(e)}

    # Stage 5: Train
    log.info("Stage 5 Train: fitting models...")
    trained = train(X_tr, X_te, y_tr, y_te, scaler, split_meta, config=cfg)
    log.info(f"  AUC={trained['metrics']['auc_test']} F1={trained['metrics']['f1_test']}")

    # Stage 6: Save
    version = save_model_to_mongo(trained, split_meta)
    if version == "rollback":
        return {"warning": "Model rolled back — previous model retained", **trained["metrics"]}

    log.info("=== MLOps Pipeline Complete ===")
    return {
        "version":       version,
        "trained_at":    datetime.utcnow().isoformat(),
        "n_train":       split_meta["n_train"],
        "n_test":        split_meta["n_test"],
        "slip_rate":     split_meta["slip_rate_train"],
        "drift_warnings":drift,
        **trained["metrics"],
    }


# ── Feature Drift Detection ───────────────────────────────────────────────────
def detect_feature_drift(df_current):
    """
    Compare current feature distributions vs last training dataset.
    Returns list of drifted features (mean shift > 1 std).
    """
    if not _mongo_available(): return []
    db = _db()
    prev_run = db["ml_runs"].find_one({"status":"active"})
    if not prev_run: return []

    prev_features = db["jira_features"].find_one({"_id":"latest"})
    if not prev_features: return []

    try:
        df_prev = pd.DataFrame(prev_features["records"])
        drifted = []
        for col in df_current.select_dtypes(include=[np.number]).columns:
            if col not in df_prev.columns: continue
            curr_mean = df_current[col].mean()
            prev_mean = df_prev[col].mean()
            prev_std  = df_prev[col].std()
            if prev_std > 0 and abs(curr_mean - prev_mean) > prev_std:
                drifted.append({"feature":col,
                                "prev_mean":round(prev_mean,3),
                                "curr_mean":round(curr_mean,3),
                                "shift_std":round(abs(curr_mean-prev_mean)/prev_std,2)})
        return drifted
    except Exception:
        return []


# ── CLI entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", choices=["pipeline","predict","status"], default="pipeline")
    parser.add_argument("--model-type", default="random_forest")
    args = parser.parse_args()

    if args.run == "pipeline":
        result = run_pipeline(config={"model_type": args.model_type})
        print(json.dumps(result, indent=2, default=str))

    elif args.run == "status":
        runs = get_model_registry()
        for r in runs:
            print(f"{r['timestamp'][:16]} | v{r.get('version','-')} | AUC={r.get('auc_test','-')} | {r['status']}")

    elif args.run == "predict":
        import data as D, ml_engine as ME
        bundle, run = load_model_from_mongo()
        if not bundle:
            print("No model found in MongoDB. Run pipeline first.")
        else:
            issues = D.get_issues()
            open_issues = [i for i in issues if i["status"] != "Closed"]
            results = ME.predict(open_issues, bundle["clf"], bundle["km"],
                                 bundle["iso"], bundle["scaler"], run)
            print(f"Predictions for {len(results)} open issues")
            for r in results[:10]:
                print(f"  {r['key']} | risk={r['delivery_risk_signal']} | {r['cluster_label']}")
