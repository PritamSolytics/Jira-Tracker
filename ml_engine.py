"""
ml_engine.py — Jira ML Engine
Handles: feature engineering, model training, inference, retraining, dataset export.
All models persist to disk via joblib. Retrain anytime from dashboard.
"""
import os, json, logging
from datetime import date, datetime
from collections import defaultdict

import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import roc_auc_score

log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
MODEL_DIR    = os.getenv("MODEL_DIR",   "/tmp/jira_models")
DATASET_PATH = os.getenv("DATASET_PATH", "/tmp/jira_dataset.csv")
RAW_PATH     = os.getenv("RAW_PATH",    "/tmp/jira_raw.json")
META_PATH    = os.path.join(MODEL_DIR, "meta.json")

os.makedirs(MODEL_DIR, exist_ok=True)

FEATURES = ["priority_score", "type_risk", "is_unassigned", "has_due", "days_open", "label_count"]

# ── Feature Engineering ────────────────────────────────────────────────────────
def engineer_features(issues: list[dict]) -> pd.DataFrame:
    """Convert raw parsed Jira issues (from data.py _parse format) to feature DataFrame."""
    rows = []
    for i in issues:
        created = i.get("created", "") or ""
        updated = i.get("updated", "") or ""
        due     = i.get("due",     "") or ""
        status  = i.get("status",  "")
        priority = i.get("priority", "") or ""
        itype    = i.get("type", "")
        labels   = i.get("labels", []) or []
        days_open = i.get("days_stale", 0)

        # Target variable: closed on time?
        closed_on_time = None
        if status == "Closed" and due:
            try:
                close_date = date.fromisoformat(updated)
                due_date   = date.fromisoformat(due)
                closed_on_time = 1 if close_date <= due_date else 0
            except Exception:
                pass

        rows.append({
            "key":            i.get("key", ""),
            "status":         status,
            "assignee":       i.get("assignee", "Unassigned"),
            "priority":       priority,
            "type":           itype,
            "created":        created,
            "updated":        updated,
            "due":            due,
            "days_open":      days_open,
            "has_due":        1 if due else 0,
            "priority_score": {"Highest":4,"High":3,"Medium":2,"Low":1,"Lowest":0}.get(priority, 2),
            "type_risk":      {"Bug":3,"Story":2,"Task":1,"Sub-task":1,"QA-Sub-task":0,"Epic":0}.get(itype, 1),
            "is_unassigned":  1 if i.get("assignee","") == "Unassigned" else 0,
            "label_count":    len(labels),
            "closed_on_time": closed_on_time,
        })
    return pd.DataFrame(rows)


def save_dataset(issues: list[dict]):
    """Build feature-engineered CSV from current issues. Call after each Jira sync."""
    df = engineer_features(issues)
    df.to_csv(DATASET_PATH, index=False)
    log.info(f"Dataset saved: {len(df)} rows → {DATASET_PATH}")
    return df


# ── Training ───────────────────────────────────────────────────────────────────
def train_models(issues: list[dict] | None = None) -> dict:
    """
    Train all 3 models. Pass issues list OR will load from CSV.
    Returns metrics dict. Saves models + meta to MODEL_DIR.
    """
    if issues is not None:
        df = save_dataset(issues)
    else:
        if not os.path.exists(DATASET_PATH):
            return {"error": "No dataset found. Run save_dataset() first."}
        df = pd.read_csv(DATASET_PATH)

    log.info(f"Training on {len(df)} rows...")

    # ── Scaler (fit on all data) ──────────────────────────────────────────────
    X_all = df[FEATURES].fillna(0)
    scaler = StandardScaler()
    scaler.fit(X_all)

    # ── 1. SLIP PREDICTOR — Random Forest ────────────────────────────────────
    train_df = df[df["closed_on_time"].notna()].copy()
    X_sup  = scaler.transform(train_df[FEATURES].fillna(0))
    y_sup  = train_df["closed_on_time"]

    X_tr, X_te, y_tr, y_te = train_test_split(
        X_sup, y_sup, test_size=0.2, random_state=42, stratify=y_sup
    )
    rf = RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")
    rf.fit(X_tr, y_tr)
    auc_test = roc_auc_score(y_te, rf.predict_proba(X_te)[:, 1])
    auc_cv   = cross_val_score(rf, X_sup, y_sup, cv=5, scoring="roc_auc").mean()
    fi       = dict(zip(FEATURES, rf.feature_importances_.round(3).tolist()))

    # ── 2. K-MEANS — Risk Clusters ───────────────────────────────────────────
    open_df = df[df["status"] != "Closed"].copy()
    n_open  = len(open_df)
    cluster_labels_map = {}
    if n_open >= 3:
        X_open = scaler.transform(open_df[FEATURES].fillna(0))
        km = KMeans(n_clusters=3, random_state=42, n_init=10)
        open_df["cluster"] = km.fit_predict(X_open)
        # Label clusters by avg priority+type risk (higher = worse)
        risk_score = open_df.groupby("cluster")[["priority_score","type_risk"]].mean().sum(axis=1)
        rank = risk_score.rank(ascending=False).astype(int)
        risk_map = {1: "🔴 Critical", 2: "🟡 Watch", 3: "🟢 Healthy"}
        cluster_labels_map = {str(c): risk_map[r] for c, r in rank.items()}
        joblib.dump(km, os.path.join(MODEL_DIR, "kmeans.pkl"))
    else:
        km = None

    # ── 3. ISOLATION FOREST — Anomaly Detection ───────────────────────────────
    iso = IsolationForest(contamination=0.1, random_state=42)
    iso.fit(X_all)
    anomaly_preds = iso.predict(X_all)
    n_anomalies   = int((anomaly_preds == -1).sum())

    # ── Save models ───────────────────────────────────────────────────────────
    joblib.dump(rf,     os.path.join(MODEL_DIR, "slip_predictor.pkl"))
    joblib.dump(scaler, os.path.join(MODEL_DIR, "scaler.pkl"))
    joblib.dump(iso,    os.path.join(MODEL_DIR, "isoforest.pkl"))

    class_balance = {str(int(k)): int(v) for k, v in y_sup.value_counts().items()}

    meta = {
        "trained_at":      datetime.now().isoformat(),
        "n_train":         int(len(train_df)),
        "n_total":         int(len(df)),
        "auc_test":        round(auc_test, 3),
        "auc_cv":          round(auc_cv, 3),
        "features":        FEATURES,
        "feature_importance": fi,
        "cluster_labels":  cluster_labels_map,
        "n_anomalies":     n_anomalies,
        "class_balance":   class_balance,
        "slip_rate":       round(int(class_balance.get("0", 0)) / len(train_df) * 100, 1),
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    log.info(f"Training complete. AUC={auc_test:.3f}")
    return meta


# ── Inference ──────────────────────────────────────────────────────────────────
def load_models():
    """Load all trained models. Returns None for each if not found."""
    def _load(name):
        path = os.path.join(MODEL_DIR, name)
        try:
            return joblib.load(path)
        except Exception:
            return None
    return {
        "rf":     _load("slip_predictor.pkl"),
        "scaler": _load("scaler.pkl"),
        "km":     _load("kmeans.pkl"),
        "iso":    _load("isoforest.pkl"),
    }


def predict_slip(issues: list[dict], models: dict | None = None) -> list[dict]:
    """
    For each open issue: predict slip probability, cluster, anomaly flag.
    Returns list of dicts with keys: key, slip_prob, cluster_label, is_anomaly.
    """
    if models is None:
        models = load_models()

    rf, scaler, km, iso = models["rf"], models["scaler"], models["km"], models["iso"]
    if rf is None or scaler is None:
        return []

    open_issues = [i for i in issues if i.get("status") != "Closed"]
    if not open_issues:
        return []

    df = engineer_features(open_issues)
    X  = scaler.transform(df[FEATURES].fillna(0))

    slip_probs    = rf.predict_proba(X)[:, 0]   # prob of NOT closing on time
    anomaly_flags = iso.predict(X) if iso else [0] * len(X)
    cluster_ids   = km.predict(X)  if km else [-1] * len(X)

    meta = get_meta()
    cluster_labels_map = meta.get("cluster_labels", {})

    results = []
    for idx, issue in enumerate(open_issues):
        results.append({
            "key":           issue["key"],
            "assignee":      issue.get("assignee", ""),
            "summary":       issue.get("summary", "")[:60],
            "status":        issue.get("status", ""),
            "priority":      issue.get("priority", ""),
            "slip_prob":     round(float(slip_probs[idx]) * 100, 1),
            "cluster_label": cluster_labels_map.get(str(int(cluster_ids[idx])), "Unknown"),
            "is_anomaly":    bool(anomaly_flags[idx] == -1),
            "days_open":     issue.get("days_stale", 0),
        })

    return sorted(results, key=lambda x: -x["slip_prob"])


def get_meta() -> dict:
    """Load model metadata (metrics, trained_at, etc.)."""
    try:
        with open(META_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def models_exist() -> bool:
    return os.path.exists(os.path.join(MODEL_DIR, "slip_predictor.pkl"))


# ── Dataset Export ─────────────────────────────────────────────────────────────
def export_dataset_csv(issues: list[dict]) -> str:
    """Save full feature-engineered CSV. Returns path."""
    df = engineer_features(issues)
    df.to_csv(DATASET_PATH, index=False)
    return DATASET_PATH
