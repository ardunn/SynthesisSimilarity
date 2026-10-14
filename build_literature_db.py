"""Build rsc_impurity/literature.db: conditions + impurity phases for the KB reactions.

One row per knowledge-base reaction (rsc_impurity/ss_rxns_kb.npz), keyed by
raw_index, with target/precursor keys built exactly as the recommender builds
them (array_to_formula over the KB composition arrays). So every reaction the
recommender knows has one row here, and nothing else does. See LITERATURE_DB.md.

    .venv/bin/python build_literature_db.py --input PATH/SS_rxns_80806.json
"""
import argparse
import datetime
import json
import os
import pickle
import sqlite3
import sys

import numpy as np

from SynthesisSimilarity.core.utils import array_to_formula, formula_to_array

REPO = os.path.dirname(os.path.abspath(__file__))
RSC = os.path.join(REPO, "SynthesisSimilarity/rsc_impurity")
KB = os.path.join(RSC, "ss_rxns_kb.npz")
SIDECAR = os.path.join(RSC, "impurity_annotations.json")
OUT = os.path.join(RSC, "literature.db")
# same vocabulary convert_ss_rxns.py used to encode the KB arrays
META = os.path.join(REPO, "SynthesisSimilarity/models/SynthesisRecommendation/model_meta.pkl")

# Heating temperatures come in deg C and K (~14% K); times in h/min/day variants.
# ponytail: fixed plausibility window, drops heating rates mis-tagged as K ("5 K/min");
# widen if you add arc-melting / SPS sources.
T_MIN_C, T_MAX_C = 100.0, 3000.0
T_MAX_H = 2000.0
TO_HOURS = {"h": 1, "hours": 1, "hour": 1, "hrs": 1, "hr": 1,
            "min": 1 / 60, "minutes": 1 / 60, "day": 24, "d": 24}

SCHEMA = """
CREATE TABLE reactions (
    raw_index      INTEGER PRIMARY KEY,  -- index in SS_rxns_80806.json == KB raw_index
    doi            TEXT,
    target         TEXT NOT NULL,        -- recommender's normalized formula (lookup key)
    precursor_key  TEXT NOT NULL,        -- '+'-joined sorted normalized precursors
    precursors     TEXT NOT NULL,        -- JSON list, normalized
    target_raw     TEXT,                 -- formula as text-mined
    precursors_raw TEXT,                 -- JSON list, as text-mined
    max_temp_C     REAL,                 -- max over Heating steps, K converted, outliers dropped
    max_time_h     REAL,                 -- longest single Heating step, hours
    impurity_state TEXT NOT NULL CHECK (impurity_state IN ('none', 'unidentified', 'named')),
    equation       TEXT,                 -- dataset's balanced target reaction, NULL if unbalanced
    coefficients   TEXT                  -- JSON {"left": {formula: coeff}, "right": {...}}
);
CREATE TABLE impurities (
    raw_index   INTEGER NOT NULL REFERENCES reactions (raw_index),
    formula     TEXT,                    -- normalized; NULL if unparseable (e.g. LixNi1-xO)
    formula_raw TEXT NOT NULL
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX idx_route ON reactions (target, precursor_key);
CREATE INDEX idx_imp ON impurities (raw_index);
"""


def norm(formula, eles):
    """Text formula -> recommender's normalized formula, or None."""
    try:
        arr = formula_to_array(formula, eles)
    except Exception:  # unparseable, or element outside the vocabulary
        return None
    return array_to_formula(arr, eles) if arr.any() else None


def heating(conditions):
    """(max temperature in deg C, longest single heating step in h) over Heating acts."""
    temps, times = [], []
    for act in conditions or []:
        if act.get("act_type") != "Heating":
            continue
        for v in act.get("temp_values") or []:
            if isinstance(v, dict) and v.get("max") is not None:
                t = v["max"] - 273.15 if v.get("units") == "K" else v["max"]
                if T_MIN_C < t <= T_MAX_C:
                    temps.append(t)
        for v in act.get("time_values") or []:
            if isinstance(v, dict) and v.get("max") is not None and v.get("units") in TO_HOURS:
                h = v["max"] * TO_HOURS[v["units"]]
                if 0 < h <= T_MAX_H:
                    times.append(h)
    return (max(temps) if temps else None), (max(times) if times else None)


def equation(raw):
    """Dataset's balanced target reaction -> (string, coefficient dict) or (None, None)."""
    tr = raw.get("target_reaction") or []
    if not tr:
        return None, None
    _, sides, _, eq = tr[0]
    try:
        coeffs = {s: {f: float(c) for f, c in (sides.get(s) or {}).items()} for s in ("left", "right")}
    except (TypeError, ValueError):
        return eq, None
    return eq, json.dumps(coeffs)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="SS_rxns_80806.json")
    args = ap.parse_args()

    with open(META, "rb") as fr:
        eles = pickle.load(fr)["config"]["all_eles"]
    kb = np.load(KB, allow_pickle=True)["train_reactions"]
    print(f"loading {args.input}")
    with open(args.input) as fr:
        data = json.load(fr)

    if os.path.exists(OUT):
        os.remove(OUT)
    con = sqlite3.connect(OUT)
    con.executescript(SCHEMA)
    for r in kb:
        i = int(r["raw_index"])
        raw = data[i]
        precs = sorted({array_to_formula(x[0], eles) for x in r["precursors_comp"]})
        phases = [m.get("material_formula") or "unknown" for m in raw.get("impurity_phase") or []]
        named = [p for p in phases if p != "unknown"]
        state = "named" if named else ("unidentified" if phases else "none")
        t_c, t_h = heating(raw.get("conditions_forDOI"))
        eq, coeffs = equation(raw)
        con.execute(
            "INSERT INTO reactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (i, r.get("doi"), array_to_formula(r["target_comp"][0], eles), "+".join(precs),
             json.dumps(precs), raw["target"][0].get("material_formula"),
             json.dumps([m.get("material_formula") for m in raw.get("precursors") or []]),
             t_c, t_h, state, eq, coeffs),
        )
        con.executemany("INSERT INTO impurities VALUES (?,?,?)",
                        [(i, norm(p, eles), p) for p in dict.fromkeys(named)])

    counts = dict(con.execute("SELECT impurity_state, COUNT(*) FROM reactions GROUP BY 1"))
    con.executemany("INSERT INTO meta VALUES (?,?)", [
        ("source", os.path.basename(args.input)),
        ("source_paper", "Lee et al., Sci. Data 12, 1969 (2025), doi:10.1038/s41597-025-06222-y"),
        ("kb", os.path.relpath(KB, REPO)),
        ("built", datetime.date.today().isoformat()),
        ("temp_window_C", f"{T_MIN_C}-{T_MAX_C}"),
        ("impurity_state_counts", json.dumps(counts)),
    ])
    con.commit()

    n = con.execute("SELECT COUNT(*) FROM reactions").fetchone()[0]
    stats = con.execute("SELECT COUNT(max_temp_C), COUNT(max_time_h), COUNT(equation), "
                        "COUNT(DISTINCT doi) FROM reactions").fetchone()
    n_imp, n_unparsed = con.execute(
        "SELECT COUNT(*), SUM(formula IS NULL) FROM impurities").fetchone()
    con.close()

    # self-check against the KB and against convert_ss_rxns.py's independent sidecar
    assert n == len(kb), (n, len(kb))
    if os.path.exists(SIDECAR):
        side = json.load(open(SIDECAR))
        assert counts.get("named", 0) + counts.get("unidentified", 0) == len(side), counts
        assert counts.get("unidentified", 0) == sum(1 for v in side.values() if not v), counts
    print(f"{n} reactions ({stats[3]} papers) -> {OUT}")
    print(f"  impurity_state: {counts}")
    print(f"  with temperature: {stats[0]}, with time: {stats[1]}, with balanced equation: {stats[2]}")
    print(f"  impurity phases: {n_imp} ({n_unparsed} unparseable, kept as formula_raw)")


if __name__ == "__main__":
    sys.exit(main())
