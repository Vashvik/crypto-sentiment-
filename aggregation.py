"""Daily sentiment aggregation per asset.

For asset a and UTC day d, with E(a, d) the eligible texts associated with a
and published in [d 00:00, d+1 00:00) UTC:

    S(a, d) = Σ wᵢ·sᵢ / Σ wᵢ        with wᵢ = 1 (equal weights, the baseline)

A day with no eligible text is stored with n_records = 0 and NULL sentiment:
missing is missing, never silently "neutral". Because a day's texts all
precede the day's close, S(a, d) is known at the close of d, which is the
moment a forecast for d+1…d+h is made.
"""

from __future__ import annotations

import pandas as pd

from app.db import IngestionLog, get_conn, utc_now


def aggregate(engine: str, symbols: list[str] | None = None) -> int:
    with IngestionLog("aggregate", f"daily:{engine}") as entry:
        with get_conn() as conn:
            df = pd.read_sql_query(
                """SELECT ta.symbol, t.published_date AS date, t.source_type, s.score, s.label
                   FROM text_records t
                   JOIN text_assets ta ON ta.text_id = t.id
                   JOIN sentiment_scores s ON s.text_id = t.id AND s.engine = ?
                   WHERE t.excluded_reason IS NULL""",
                conn,
                params=(engine,),
            )
        if symbols:
            df = df[df["symbol"].isin(symbols)]
        daily = aggregate_frame(df)
        daily = _fill_missing_days(daily, df, symbols)
        now = utc_now()
        rows = [
            (
                r.symbol, r.date, engine, int(r.n_records), int(r.n_news), int(r.n_social),
                _f(r.sent_mean), _f(r.sent_std), _f(r.pos_prop), _f(r.neu_prop), _f(r.neg_prop),
                _f(r.sent_news), _f(r.sent_social), now,
            )
            for r in daily.itertuples(index=False)
        ]
        with get_conn() as conn:
            conn.execute("DELETE FROM daily_sentiment WHERE engine = ?" + (" AND symbol IN (%s)" % ",".join("?" * len(symbols)) if symbols else ""),
                         (engine, *(symbols or [])))
            conn.executemany(
                """INSERT INTO daily_sentiment(symbol, date, engine, n_records, n_news, n_social, sent_mean, sent_std,
                       pos_prop, neu_prop, neg_prop, sent_news, sent_social, computed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
        entry.n_inserted = len(rows)
        return len(rows)


def aggregate_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Pure aggregation (tested directly). Input columns: symbol, date,
    source_type, score, label."""
    cols = ["symbol", "date", "n_records", "n_news", "n_social", "sent_mean", "sent_std",
            "pos_prop", "neu_prop", "neg_prop", "sent_news", "sent_social"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    g = df.groupby(["symbol", "date"])
    out = g.agg(
        n_records=("score", "size"),
        sent_mean=("score", "mean"),
        sent_std=("score", "std"),
    )
    out["n_news"] = g["source_type"].apply(lambda s: int((s == "news").sum()))
    out["n_social"] = g["source_type"].apply(lambda s: int((s == "social").sum()))
    for label, col in (("positive", "pos_prop"), ("neutral", "neu_prop"), ("negative", "neg_prop")):
        out[col] = g["label"].apply(lambda s, label=label: float((s == label).mean()))
    by_type = df.pivot_table(index=["symbol", "date"], columns="source_type", values="score", aggfunc="mean")
    out["sent_news"] = by_type["news"] if "news" in by_type else float("nan")
    out["sent_social"] = by_type["social"] if "social" in by_type else float("nan")
    return out.reset_index()[cols]


def _fill_missing_days(daily: pd.DataFrame, raw: pd.DataFrame, symbols) -> pd.DataFrame:
    """Adds explicit zero-count rows for days inside the asset's text coverage
    window (first → last day any text was collected) that had no eligible
    text. Days outside that window get no row at all, so "the collector was
    not running" stays distinguishable from "nothing was published"."""
    frames = []
    for symbol, group in daily.groupby("symbol"):
        if symbols and symbol not in symbols:
            continue
        first = group["date"].min()
        last = raw["date"].max() if not raw.empty else group["date"].max()
        idx = pd.date_range(first, max(last, group["date"].max()), freq="D").strftime("%Y-%m-%d")
        g = group.set_index("date").reindex(idx)
        g.index.name = "date"
        g["symbol"] = symbol
        for col in ("n_records", "n_news", "n_social"):
            g[col] = g[col].fillna(0).astype(int)
        frames.append(g.reset_index())
    return pd.concat(frames, ignore_index=True) if frames else daily


def _f(v):
    return None if v is None or pd.isna(v) else float(v)


def daily_sentiment(symbol: str, engine: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    q = "SELECT * FROM daily_sentiment WHERE symbol = ? AND engine = ?"
    params: list = [symbol, engine]
    if start:
        q += " AND date >= ?"; params.append(start)
    if end:
        q += " AND date <= ?"; params.append(end)
    with get_conn() as conn:
        df = pd.read_sql_query(q + " ORDER BY date", conn, params=params)
    return df
