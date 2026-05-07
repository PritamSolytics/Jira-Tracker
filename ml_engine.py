"""
ml_engine.py — Predictive Analytics Engine
Feature engineering, model training, inference, retraining, dataset export,
time series forecasting (ARIMA/SARIMA), statistical tests.
"""
import os, json, logging, warnings
warnings.filterwarnings("ignore")
from datetime import date, datetime, timedelta
from collections import defaultdict, Counter

import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import RandomForestClassifier, IsolationForest, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.metrics import roc_auc_score

log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
DATA_DIR     = os.getenv("DATA_DIR",     "data")
MODEL_DIR    = os.getenv("MODEL_DIR",    os.path.join(DATA_DIR, "models"))
DATASET_PATH = os.getenv("DATASET_PATH", os.path.join(DATA_DIR, "jira_dataset.csv"))
META_PATH    = os.path.join(MODEL_DIR, "meta.json")

for d in [DATA_DIR, MODEL_DIR]:
    os.makedirs(d, exist_ok=True)

FEATURES_BASE = [
    "priority_score", "type_risk", "is_unassigned", "has_due",
    "days_open", "label_count", "link_count", "blocker_count",
    "blocked_count", "comment_count",
]
FEATURES_GRAPH = ["degree_centrality", "betweenness_centrality", "assignee_load"]
ALL_FEATURES   = FEATURES_BASE + FEATURES_GRAPH


# ── Graph Centrality ───────────────────────────────────────────────────────────
def compute_graph_features(issues):
    try:
        import networkx as nx
        G = nx.DiGraph()
        for i in issues:
            G.add_node(i["key"])
            for lnk in i.get("links", []):
                if lnk["direction"] == "outward":
                    G.add_edge(i["key"], lnk.get("key", ""))
        deg = nx.degree_centrality(G)
        try:
            bet = nx.betweenness_centrality(G, normalized=True)
        except Exception:
            bet = {n: 0.0 for n in G.nodes}
        return {"degree": deg, "betweenness": bet}
    except Exception:
        return {"degree": {}, "betweenness": {}}


# ── Feature Engineering ────────────────────────────────────────────────────────
def engineer_features(issues):
    assignee_load = defaultdict(int)
    for i in issues:
        if i.get("status") != "Closed":
            assignee_load[i.get("assignee", "Unassigned")] += 1

    blocker_count = defaultdict(int)
    blocked_count = defaultdict(int)
    for i in issues:
        for lnk in i.get("links", []):
            if "block" in lnk.get("type", "").lower():
                if lnk["direction"] == "outward":
                    blocker_count[i["key"]] += 1
                else:
                    blocked_count[i["key"]] += 1

    graph_feats = compute_graph_features(issues)
    deg = graph_feats["degree"]
    bet = graph_feats["betweenness"]

    rows = []
    for i in issues:
        created  = i.get("created", "") or ""
        updated  = i.get("updated", "") or ""
        due      = i.get("due", "") or ""
        status   = i.get("status", "")
        priority = i.get("priority", "") or ""
        itype    = i.get("type", "")
        labels   = i.get("labels", []) or []
        links    = i.get("links", []) or []

        closed_on_time = None
        if status == "Closed" and due:
            try:
                closed_on_time = 1 if date.fromisoformat(updated) <= date.fromisoformat(due) else 0
            except Exception:
                pass

        cycle_time = None
        if status == "Closed" and created and updated:
            try:
                cycle_time = (date.fromisoformat(updated) - date.fromisoformat(created)).days
            except Exception:
                pass

        rows.append({
            "key":                    i.get("key", ""),
            "status":                 status,
            "assignee":               i.get("assignee", "Unassigned"),
            "priority":               priority,
            "type":                   itype,
            "created":                created,
            "updated":                updated,
            "due":                    due,
            "fix_version":            i.get("fix_version", "") or "",
            "days_open":              i.get("days_stale", 0),
            "cycle_time":             cycle_time,
            "has_due":                1 if due else 0,
            "priority_score":         {"Highest":4,"High":3,"Medium":2,"Low":1,"Lowest":0}.get(priority, 2),
            "type_risk":              {"Bug":3,"Story":2,"Task":1,"Sub-task":1,"QA-Sub-task":0,"Epic":0}.get(itype, 1),
            "is_unassigned":          1 if i.get("assignee","") == "Unassigned" else 0,
            "label_count":            len(labels),
            "link_count":             len(links),
            "blocker_count":          blocker_count.get(i.get("key",""), 0),
            "blocked_count":          blocked_count.get(i.get("key",""), 0),
            "comment_count":          i.get("comments_count", 0),
            "degree_centrality":      round(deg.get(i.get("key",""), 0.0), 4),
            "betweenness_centrality": round(bet.get(i.get("key",""), 0.0), 4),
            "assignee_load":          assignee_load.get(i.get("assignee","Unassigned"), 0),
            "closed_on_time":         closed_on_time,
        })
    return pd.DataFrame(rows)


def save_dataset(issues):
    df = engineer_features(issues)
    df.to_csv(DATASET_PATH, index=False)
    return df


# ── Training ───────────────────────────────────────────────────────────────────
def train_models(issues=None, config=None):
    cfg = {
        "n_estimators": 200, "max_depth": None, "test_size": 0.2,
        "n_clusters": 3, "contamination": 0.1, "model_type": "random_forest",
    }
    if config:
        cfg.update({k: v for k, v in config.items() if v is not None})

    if issues is not None:
        df = save_dataset(issues)
    else:
        if not os.path.exists(DATASET_PATH):
            return {"error": "No dataset. Run Retrain with live data."}
        df = pd.read_csv(DATASET_PATH)

    features = [f for f in ALL_FEATURES if f in df.columns]
    X_all = df[features].fillna(0)
    scaler = StandardScaler()
    scaler.fit(X_all)

    results = {}

    # ── Slip Predictor ────────────────────────────────────────────────────────
    train_df = df[df["closed_on_time"].notna()].copy()
    if len(train_df) >= 20:
        X_sup = scaler.transform(train_df[features].fillna(0))
        y_sup = train_df["closed_on_time"]
        X_tr, X_te, y_tr, y_te = train_test_split(
            X_sup, y_sup, test_size=float(cfg["test_size"]), random_state=42, stratify=y_sup)

        if cfg["model_type"] == "gradient_boosting":
            clf = GradientBoostingClassifier(
                n_estimators=int(cfg["n_estimators"]),
                max_depth=int(cfg["max_depth"]) if cfg["max_depth"] else 3,
                random_state=42)
        elif cfg["model_type"] == "logistic":
            clf = LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced")
        else:
            clf = RandomForestClassifier(
                n_estimators=int(cfg["n_estimators"]),
                max_depth=int(cfg["max_depth"]) if cfg["max_depth"] else None,
                random_state=42, class_weight="balanced")

        clf.fit(X_tr, y_tr)
        auc_test = round(roc_auc_score(y_te, clf.predict_proba(X_te)[:, 1]), 3)
        cv_scores = cross_val_score(clf, X_sup, y_sup, cv=StratifiedKFold(5), scoring="roc_auc")

        if hasattr(clf, "feature_importances_"):
            fi = dict(zip(features, clf.feature_importances_.round(4).tolist()))
        else:
            raw = [abs(c) for c in clf.coef_[0]]
            total = sum(raw) or 1
            fi = dict(zip(features, [round(v/total, 4) for v in raw]))

        joblib.dump(clf, os.path.join(MODEL_DIR, "slip_predictor.pkl"))
        results.update({
            "auc_test": auc_test, "auc_cv": round(cv_scores.mean(), 3),
            "auc_cv_std": round(cv_scores.std(), 3),
            "n_train": int(len(train_df)), "feature_importance": fi,
            "features_used": features,
            "class_balance": {str(int(k)): int(v) for k, v in y_sup.value_counts().items()},
            "slip_rate": round(int(y_sup.value_counts().get(0.0, 0)) / len(train_df) * 100, 1),
            "model_type": cfg["model_type"],
        })
    else:
        results.update({"auc_test": None, "auc_cv": None, "n_train": 0})

    # ── K-Means Clusters ──────────────────────────────────────────────────────
    open_df = df[df["status"] != "Closed"].copy()
    cluster_labels_map = {}
    if len(open_df) >= int(cfg["n_clusters"]):
        X_open = scaler.transform(open_df[features].fillna(0))
        km = KMeans(n_clusters=int(cfg["n_clusters"]), random_state=42, n_init=10)
        clusters = km.fit_predict(X_open)
        open_df = open_df.copy()
        open_df["cluster"] = clusters
        risk = open_df.groupby("cluster")[["priority_score","blocker_count","days_open"]].mean().sum(axis=1)
        rank = risk.rank(ascending=False).astype(int)
        risk_labels = {1: "Critical", 2: "Elevated", 3: "Standard"}
        cluster_labels_map = {str(c): risk_labels.get(r, "Standard") for c, r in rank.items()}
        joblib.dump(km, os.path.join(MODEL_DIR, "kmeans.pkl"))
    results["cluster_labels"] = cluster_labels_map

    # ── Isolation Forest ──────────────────────────────────────────────────────
    iso = IsolationForest(contamination=float(cfg["contamination"]), random_state=42)
    iso.fit(scaler.transform(X_all))
    results["n_anomalies"] = int((iso.predict(scaler.transform(X_all)) == -1).sum())
    joblib.dump(iso, os.path.join(MODEL_DIR, "isoforest.pkl"))
    joblib.dump(scaler, os.path.join(MODEL_DIR, "scaler.pkl"))

    meta = {"trained_at": datetime.now().isoformat(), "n_total": int(len(df)), "config": cfg, **results}
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)
    return meta


# ── Inference ──────────────────────────────────────────────────────────────────
def load_models():
    def _l(n):
        try: return joblib.load(os.path.join(MODEL_DIR, n))
        except: return None
    return {k: _l(v) for k, v in {"rf":"slip_predictor.pkl","scaler":"scaler.pkl","km":"kmeans.pkl","iso":"isoforest.pkl"}.items()}


def predict_slip(issues, models=None):
    if models is None: models = load_models()
    clf, scaler, km, iso = models["rf"], models["scaler"], models["km"], models["iso"]
    if clf is None or scaler is None: return []

    open_issues = [i for i in issues if i.get("status") != "Closed"]
    if not open_issues: return []

    meta = get_meta()
    features = meta.get("features_used", ALL_FEATURES)
    df = engineer_features(open_issues)
    avail = [f for f in features if f in df.columns]
    X = scaler.transform(df[avail].fillna(0))

    slip_probs    = clf.predict_proba(X)[:, 0]
    anomaly_flags = iso.predict(X) if iso else [0]*len(X)
    cluster_ids   = km.predict(X) if km else [-1]*len(X)
    clmap         = meta.get("cluster_labels", {})

    results = []
    for idx, issue in enumerate(open_issues):
        results.append({
            "key":           issue["key"],
            "assignee":      issue.get("assignee", ""),
            "summary":       issue.get("summary", "")[:70],
            "status":        issue.get("status", ""),
            "priority":      issue.get("priority", ""),
            "type":          issue.get("type", ""),
            "slip_prob":     round(float(slip_probs[idx]) * 100, 1),
            "cluster_label": clmap.get(str(int(cluster_ids[idx])), "Standard"),
            "is_anomaly":    bool(anomaly_flags[idx] == -1),
            "days_open":     issue.get("days_stale", 0),
            "blocker_count": int(df.iloc[idx].get("blocker_count", 0)),
            "degree_centrality": round(float(df.iloc[idx].get("degree_centrality", 0)), 4),
        })
    return sorted(results, key=lambda x: -x["slip_prob"])


def get_meta():
    try:
        with open(META_PATH) as f: return json.load(f)
    except: return {}


def models_exist():
    return os.path.exists(os.path.join(MODEL_DIR, "slip_predictor.pkl"))


def get_dataset():
    try: return pd.read_csv(DATASET_PATH)
    except: return None


# ── Time Series Forecasting ────────────────────────────────────────────────────
def forecast_velocity(issues, periods=8):
    closed = [i for i in issues if i.get("status") == "Closed" and i.get("updated")]
    by_week = Counter()
    for i in closed:
        try:
            d = date.fromisoformat(i["updated"])
            week = d - timedelta(days=d.weekday())
            by_week[str(week)] += 1
        except: pass

    weeks = sorted(by_week)[-24:]
    if len(weeks) < 8:
        return {"error": "Insufficient history (need 8+ weeks of closed issues)"}

    y = np.array([by_week[w] for w in weeks], dtype=float)

    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        from statsmodels.tsa.stattools import adfuller

        adf = adfuller(y, autolag="AIC")
        is_stationary = adf[1] < 0.05
        d_order = 0 if is_stationary else 1

        try:
            model = SARIMAX(y, order=(1, d_order, 1), seasonal_order=(1, 0, 1, 4),
                           enforce_stationarity=False, enforce_invertibility=False)
            fit = model.fit(disp=False)
            name = f"SARIMA(1,{d_order},1)(1,0,1,4)"
        except Exception:
            model = SARIMAX(y, order=(1, d_order, 1))
            fit = model.fit(disp=False)
            name = f"ARIMA(1,{d_order},1)"

        fc = fit.get_forecast(steps=periods)
        fc_mean = fc.predicted_mean
        fc_ci   = fc.conf_int(alpha=0.2)
        last = date.fromisoformat(weeks[-1])
        future = [str(last + timedelta(weeks=i+1)) for i in range(periods)]

        return {
            "actual_weeks":    weeks,
            "actual_values":   y.tolist(),
            "forecast_weeks":  future,
            "forecast_values": [round(max(0,v),1) for v in fc_mean.tolist()],
            "ci_lower":        [round(max(0,v),1) for v in (fc_ci[:,0] if isinstance(fc_ci, __import__("numpy").ndarray) else fc_ci.iloc[:,0]).tolist()],
            "ci_upper":        [round(max(0,v),1) for v in (fc_ci[:,1] if isinstance(fc_ci, __import__("numpy").ndarray) else fc_ci.iloc[:,1]).tolist()],
            "model_name": name, "aic": round(fit.aic, 2),
            "is_stationary": is_stationary, "adf_pvalue": round(adf[1], 4),
        }
    except Exception as e:
        return {"error": str(e)}


# ── Statistical Tests ─────────────────────────────────────────────────────────
def run_statistical_tests(issues):
    results = {}

    # ADF on velocity
    try:
        from statsmodels.tsa.stattools import adfuller
        closed = [i for i in issues if i.get("status") == "Closed" and i.get("updated")]
        by_week = Counter()
        for i in closed:
            try:
                d = date.fromisoformat(i["updated"])
                week = d - timedelta(days=d.weekday())
                by_week[str(week)] += 1
            except: pass
        weeks = sorted(by_week)[-20:]
        if len(weeks) >= 8:
            y = [by_week[w] for w in weeks]
            stat, pval, _, _, crit, _ = adfuller(y)
            results["adf"] = {
                "test": "Augmented Dickey-Fuller (Velocity Stationarity)",
                "statistic": round(stat, 4), "p_value": round(pval, 4),
                "critical_5pct": round(crit["5%"], 4),
                "conclusion": "Stationary — suitable for ARIMA" if pval < 0.05 else "Non-stationary — differencing applied",
            }
    except Exception as e:
        results["adf"] = {"error": str(e)}

    # Shapiro-Wilk on cycle times
    try:
        from scipy import stats as spstats
        df = get_dataset()
        if df is not None and "cycle_time" in df.columns:
            ct = df[df["cycle_time"].notna()]["cycle_time"].values
            if len(ct) >= 10:
                stat, pval = spstats.shapiro(ct[:50])
                results["shapiro"] = {
                    "test": "Shapiro-Wilk (Cycle Time Normality)",
                    "statistic": round(stat, 4), "p_value": round(pval, 4),
                    "n": int(len(ct)), "mean_days": round(float(ct.mean()), 1),
                    "std_days": round(float(ct.std()), 1),
                    "median_days": round(float(np.median(ct)), 1),
                    "conclusion": "Normal distribution" if pval > 0.05 else "Non-normal — use non-parametric tests",
                }
    except Exception as e:
        results["shapiro"] = {"error": str(e)}

    # Mann-Whitney: High vs Medium priority cycle time
    try:
        from scipy import stats as spstats
        df = get_dataset()
        if df is not None and "cycle_time" in df.columns:
            high = df[(df["priority"]=="High") & df["cycle_time"].notna()]["cycle_time"].values
            med  = df[(df["priority"]=="Medium") & df["cycle_time"].notna()]["cycle_time"].values
            if len(high) >= 5 and len(med) >= 5:
                stat, pval = spstats.mannwhitneyu(high, med, alternative="two-sided")
                results["mannwhitney"] = {
                    "test": "Mann-Whitney U (High vs Medium Priority — Cycle Time)",
                    "statistic": round(stat, 2), "p_value": round(pval, 4),
                    "high_median": round(float(np.median(high)), 1),
                    "medium_median": round(float(np.median(med)), 1),
                    "conclusion": "Significant difference in cycle time by priority" if pval < 0.05 else "No significant difference",
                }
    except Exception as e:
        results["mannwhitney"] = {"error": str(e)}

    # Kruskal-Wallis: cycle time across bug/task/story
    try:
        from scipy import stats as spstats
        df = get_dataset()
        if df is not None and "cycle_time" in df.columns:
            groups = {t: df[(df["type"]==t) & df["cycle_time"].notna()]["cycle_time"].values
                      for t in ["Bug","Task","Story","Sub-task"]}
            groups = {k: v for k, v in groups.items() if len(v) >= 5}
            if len(groups) >= 2:
                stat, pval = spstats.kruskal(*groups.values())
                results["kruskal"] = {
                    "test": "Kruskal-Wallis (Cycle Time by Issue Type)",
                    "statistic": round(stat, 4), "p_value": round(pval, 4),
                    "groups_compared": list(groups.keys()),
                    "group_medians": {k: round(float(np.median(v)),1) for k,v in groups.items()},
                    "conclusion": "Significant difference across issue types" if pval < 0.05 else "No significant difference",
                }
    except Exception as e:
        results["kruskal"] = {"error": str(e)}

    return results
