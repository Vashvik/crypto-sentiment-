"""Text sentiment engines, scoring and engine evaluation.

Engines (all return a score in [-1, 1] plus a label):
- vader        : VADER lexicon (Hutto & Gilbert, 2014). Fast, transparent baseline.
- vader_crypto : VADER plus a small, documented crypto-market lexicon
                 (bullish, bearish, rally, plunge, hack, liquidation …).
- crypto_lr    : TF-IDF + logistic regression trained on CryptoPanic community
                 votes (positive vs negative) using ONLY headlines published on
                 or before SENTIMENT_LABEL_CUTOFF, i.e. before the forecasting
                 study period starts, so its training labels never overlap the
                 period it is used to score for forecasting.
- finbert      : ProsusAI/finbert transformer (optional; needs
                 `pip install -r requirements-finbert.txt` and a one-off model
                 download from Hugging Face).

Engine choice is made on evidence: every available engine is scored against
held-out community-vote labels from the validation period, and `auto` picks
the one with the highest validation ROC-AUC. Test-period agreement is
reported but never used for the choice.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app.config import BACKEND_DIR, settings
from app.db import IngestionLog, get_conn, get_state, set_state, utc_now

log = logging.getLogger("cryptosentinel.sentiment")

MODEL_DIR = BACKEND_DIR / "data" / "models"
CRYPTO_LR_PATH = MODEL_DIR / "crypto_lr.joblib"
ALL_ENGINES = ("vader", "vader_crypto", "crypto_lr", "finbert")
NEUTRAL_BAND = 0.05  # |score| below this is "neutral" (VADER's standard threshold)

# Valence on VADER's −4…+4 scale. Words chosen for unambiguous direction in
# crypto-market headlines; deliberately short so it stays reviewable.
CRYPTO_LEXICON = {
    "bullish": 2.0, "bearish": -2.0, "rally": 1.8, "rallies": 1.8, "rallied": 1.8,
    "surge": 1.8, "surges": 1.8, "surged": 1.8, "soar": 2.0, "soars": 2.0, "soared": 2.0,
    "skyrocket": 2.3, "skyrockets": 2.3, "breakout": 1.5, "rebound": 1.5, "rebounds": 1.5,
    "recovery": 1.3, "recovers": 1.3, "inflows": 1.0, "adoption": 1.2, "approval": 1.5,
    "approved": 1.5, "approves": 1.5, "ath": 1.5, "mooning": 1.6, "hodl": 0.6,
    "dump": -1.8, "dumps": -1.8, "dumped": -1.8, "plunge": -2.2, "plunges": -2.2, "plunged": -2.2,
    "plummet": -2.3, "plummets": -2.3, "plummeted": -2.3, "tumble": -1.8, "tumbles": -1.8,
    "slump": -1.8, "slumps": -1.8, "selloff": -1.8, "sell-off": -1.8, "liquidation": -1.5,
    "liquidations": -1.5, "liquidated": -1.6, "hack": -2.2, "hacked": -2.3, "exploit": -2.0,
    "exploited": -2.0, "rugpull": -2.5, "fud": -1.5, "outflows": -1.0, "capitulation": -2.0,
    "bloodbath": -2.5, "crackdown": -1.8, "lawsuit": -1.5, "sues": -1.5, "sued": -1.5,
    "ban": -1.6, "bans": -1.6, "banned": -1.8, "delisting": -1.6, "insolvency": -2.2,
    "bankruptcy": -2.3, "bankrupt": -2.3,
}


# ── Engines ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=2)
def _vader(crypto: bool):
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    analyzer = SentimentIntensityAnalyzer()
    if crypto:
        analyzer.lexicon.update(CRYPTO_LEXICON)
    return analyzer


def _label(score: float) -> str:
    if score >= NEUTRAL_BAND:
        return "positive"
    if score <= -NEUTRAL_BAND:
        return "negative"
    return "neutral"


def _score_vader(texts: list[str], crypto: bool) -> list[dict]:
    analyzer = _vader(crypto)
    out = []
    for t in texts:
        s = analyzer.polarity_scores(t)
        out.append({"score": s["compound"], "p_pos": s["pos"], "p_neu": s["neu"], "p_neg": s["neg"], "label": _label(s["compound"])})
    return out


@lru_cache(maxsize=1)
def _crypto_lr():
    if not CRYPTO_LR_PATH.exists():
        raise RuntimeError("crypto_lr model not trained yet (run the 'train-text-model' step)")
    return joblib.load(CRYPTO_LR_PATH)


def _score_crypto_lr(texts: list[str]) -> list[dict]:
    bundle = _crypto_lr()
    p = bundle["model"].predict_proba(texts)[:, list(bundle["model"].classes_).index(1)]
    out = []
    for prob in p:
        score = float(2 * prob - 1)
        out.append({"score": score, "p_pos": float(prob), "p_neu": None, "p_neg": float(1 - prob), "label": _label_lr(score)})
    return out


def _label_lr(score: float) -> str:
    # The classifier is two-class; a probability near 0.5 means "no clear direction".
    if score >= 0.2:
        return "positive"
    if score <= -0.2:
        return "negative"
    return "neutral"


@lru_cache(maxsize=1)
def _finbert():
    try:
        from transformers import pipeline  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("FinBERT needs the optional packages: pip install -r requirements-finbert.txt") from exc
    return pipeline("text-classification", model="ProsusAI/finbert", top_k=None, truncation=True)


def _score_finbert(texts: list[str]) -> list[dict]:  # pragma: no cover - optional dependency
    clf = _finbert()
    out = []
    for i in range(0, len(texts), 32):
        for result in clf(texts[i : i + 32]):
            probs = {r["label"].lower(): float(r["score"]) for r in result}
            score = probs.get("positive", 0.0) - probs.get("negative", 0.0)
            label = max(probs, key=probs.get)
            out.append({"score": score, "p_pos": probs.get("positive"), "p_neu": probs.get("neutral"),
                        "p_neg": probs.get("negative"), "label": label})
    return out


def score_texts(engine: str, texts: list[str]) -> list[dict]:
    if engine == "vader":
        return _score_vader(texts, crypto=False)
    if engine == "vader_crypto":
        return _score_vader(texts, crypto=True)
    if engine == "crypto_lr":
        return _score_crypto_lr(texts)
    if engine == "finbert":
        return _score_finbert(texts)
    raise ValueError(f"unknown sentiment engine '{engine}'")


def engine_available(engine: str) -> tuple[bool, str]:
    try:
        score_texts(engine, ["Bitcoin price rises after ETF approval"])
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# ── Supervised crypto engine ───────────────────────────────────────────────

def vote_labels(df: pd.DataFrame) -> pd.Series:
    """Community-vote label: 1 = clearly positive, 0 = clearly negative,
    NaN = too few or mixed votes. Needs at least two votes on the winning side
    and a 2:1 margin."""
    vp = df["votes_positive"].fillna(0)
    vn = df["votes_negative"].fillna(0)
    label = pd.Series(np.nan, index=df.index)
    label[(vp >= 2) & (vp >= 2 * vn)] = 1
    label[(vn >= 2) & (vn >= 2 * vp)] = 0
    return label


def labelled_texts() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            """SELECT id, published_date, title, votes_positive, votes_negative
               FROM text_records
               WHERE excluded_reason IS NULL AND votes_positive IS NOT NULL""",
            conn,
        )
    df["label"] = vote_labels(df)
    return df.dropna(subset=["label"])


def train_crypto_lr() -> dict:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    with IngestionLog("sentiment", "train:crypto_lr") as entry:
        df = labelled_texts()
        train = df[df["published_date"] <= settings.sentiment_label_cutoff]
        entry.n_fetched = len(train)
        if len(train) < 300 or train["label"].nunique() < 2:
            entry.status = "skipped"
            entry.message = f"only {len(train)} labelled headlines before {settings.sentiment_label_cutoff}"
            return {"trained": False, "reason": entry.message}
        model = make_pipeline(
            TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=2, max_features=30000, sublinear_tf=True),
            LogisticRegression(C=2.0, class_weight="balanced", max_iter=2000, random_state=settings.random_seed),
        )
        model.fit(train["title"].tolist(), train["label"].astype(int).to_numpy())
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        meta = {
            "trained_at": utc_now(),
            "label_cutoff": settings.sentiment_label_cutoff,
            "n_train": int(len(train)),
            "positive_share": float(train["label"].mean()),
            "first_date": train["published_date"].min(),
            "last_date": train["published_date"].max(),
        }
        joblib.dump({"model": model, "meta": meta}, CRYPTO_LR_PATH)
        _crypto_lr.cache_clear()
        set_state("crypto_lr_meta", json.dumps(meta))
        entry.n_inserted = len(train)
        entry.message = f"trained on {len(train)} headlines up to {meta['last_date']}"
        return {"trained": True, **meta}


def evaluate_engines(engines: list[str] | None = None) -> dict:
    """Agreement of each engine with held-out community-vote labels."""
    from sklearn.metrics import f1_score, roc_auc_score

    df = labelled_texts()
    segments = {
        "validation": df[(df["published_date"] >= settings.study_start) & (df["published_date"] <= settings.validation_end)],
        "test": df[df["published_date"] > settings.validation_end],
    }
    results: dict[str, dict] = {}
    for engine in engines or list(ALL_ENGINES):
        ok, why = engine_available(engine)
        if not ok:
            results[engine] = {"available": False, "reason": why}
            continue
        results[engine] = {"available": True}
        for seg, data in segments.items():
            if len(data) < 30 or data["label"].nunique() < 2:
                results[engine][seg] = {"n": int(len(data)), "note": "too few labelled headlines"}
                continue
            scores = np.array([r["score"] for r in score_texts(engine, data["title"].tolist())])
            y = data["label"].astype(int).to_numpy()
            pred = (scores > 0).astype(int)
            decided = np.abs(scores) >= NEUTRAL_BAND
            metrics = {
                "n": int(len(y)),
                "positive_share": float(y.mean()),
                "roc_auc": float(roc_auc_score(y, scores)),
                "macro_f1_sign": float(f1_score(y, pred, average="macro")),
                "accuracy_sign": float((pred == y).mean()),
                "coverage_non_neutral": float(decided.mean()),
                "accuracy_when_decided": float((pred[decided] == y[decided]).mean()) if decided.any() else None,
            }
            results[engine][seg] = metrics
            with get_conn() as conn:
                conn.execute(
                    """INSERT INTO sentiment_engine_evaluations(evaluated_at, engine, segment, n, metrics_json)
                       VALUES (?,?,?,?,?) ON CONFLICT(engine, segment) DO UPDATE SET
                       evaluated_at=excluded.evaluated_at, n=excluded.n, metrics_json=excluded.metrics_json""",
                    (utc_now(), engine, seg, metrics["n"], json.dumps(metrics)),
                )
    candidates = {
        e: r["validation"]["roc_auc"]
        for e, r in results.items()
        if r.get("available") and isinstance(r.get("validation"), dict) and "roc_auc" in r["validation"]
    }
    selected = max(candidates, key=candidates.get) if candidates else "vader"
    set_state("selected_sentiment_engine", selected)
    set_state("sentiment_engine_selection", json.dumps({"selected": selected, "criterion": "validation ROC-AUC vs community votes", "scores": candidates, "at": utc_now()}))
    return {"selected": selected, "criterion": "highest validation ROC-AUC against community-vote labels", "engines": results}


def active_engine() -> str:
    """The engine used for aggregation and forecasting."""
    if settings.sentiment_engine != "auto":
        return settings.sentiment_engine
    return get_state("selected_sentiment_engine", "vader") or "vader"


# ── Scoring stored texts ───────────────────────────────────────────────────

def score_pending(engine: str, batch_size: int = 2000) -> int:
    """Scores every eligible text that has no score for this engine yet."""
    total = 0
    with IngestionLog("sentiment", f"score:{engine}") as entry:
        while True:
            with get_conn() as conn:
                rows = conn.execute(
                    """SELECT t.id, t.clean_text FROM text_records t
                       LEFT JOIN sentiment_scores s ON s.text_id = t.id AND s.engine = ?
                       WHERE s.text_id IS NULL AND t.excluded_reason IS NULL
                       LIMIT ?""",
                    (engine, batch_size),
                ).fetchall()
            if not rows:
                break
            scored = score_texts(engine, [r["clean_text"] for r in rows])
            now = utc_now()
            with get_conn() as conn:
                conn.executemany(
                    """INSERT OR REPLACE INTO sentiment_scores(text_id, engine, score, p_pos, p_neu, p_neg, label, scored_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    [(r["id"], engine, s["score"], s["p_pos"], s["p_neu"], s["p_neg"], s["label"], now) for r, s in zip(rows, scored)],
                )
            total += len(rows)
        entry.n_inserted = total
    return total


def score_single(text: str, engine: str | None = None) -> dict:
    from app.services.text_processing import clean_text, tag_assets

    engine = engine or active_engine()
    cleaned = clean_text(text)
    result = score_texts(engine, [cleaned])[0]
    return {"engine": engine, "text": cleaned, "assets": sorted(tag_assets(cleaned)), **result}
