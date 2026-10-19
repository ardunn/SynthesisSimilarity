# literature.db

Synthesis conditions and impurity phases for every reaction in the knowledge base
(`rsc_impurity/ss_rxns_kb.npz`), used by `get_literature_recipes` and `route_impurities`
in `mcp_server.py`. The model itself does not see impurities yet (planned retrain).

**Source:** `SS_rxns_80806.json`, Lee et al., *Sci. Data* 12, 1969 (2025),
[doi:10.1038/s41597-025-06222-y](https://doi.org/10.1038/s41597-025-06222-y).
80,806 reactions, every one checked for impurities by the paper's LLM extraction
(impurity-phase F1 0.88, 0.93 on balanced reactions).

## Build

```bash
.venv/bin/python convert_ss_rxns.py --input PATH/SS_rxns_80806.json     # KB + impurity sidecar
.venv/bin/python build_literature_db.py --input PATH/SS_rxns_80806.json # -> rsc_impurity/literature.db (~35 s)
```

`build_literature_db.py` writes one row per KB reaction, keyed by `raw_index` (the record's
index in the source JSON), with target and precursor keys built the same way the recommender
builds them. It checks itself against the KB and against `impurity_annotations.json`.
Like the rest of `rsc_impurity/`, the db is data (gitignored), not code.

## What was kept (66,154 of 80,806 reactions; 46,816 papers)

`convert_ss_rxns.py` dropped 14,652 records:

| Reason | Records |
|---|---|
| No target formula (a name or notation, e.g. `V(C,N)`, `BGO (Bismuth Germanate)`) | 9,914 |
| No parsed composition (abbreviations like `CZTS`, `YBCO`; also some real formulas) | 3,401 |
| Placeholder elements (`R2O3`, `RE`, `M`) | 1,032 |
| Variable amounts (`CrCx`, `MgCl2·nH2O`) | 256 |
| Element outside the model's 83-element vocabulary (mostly acetate written `Ac`) | 49 |

## Tables

- **reactions**: `raw_index`, `doi`, `target` / `precursor_key` / `precursors` (normalized
  lookup keys), `target_raw` / `precursors_raw` (as text-mined), `max_temp_C`, `max_time_h`,
  `impurity_state`, `equation` + `coefficients` (the dataset's balanced target reaction, NULL
  for the ~21% the extractor could not balance).
- **impurities**: `raw_index`, `formula` (normalized; NULL for 350 unparseable such as
  `LixNi1-xO`), `formula_raw`.
- **meta**: source, build date, temperature window, state counts.

## Semantics

- **`impurity_state`**: `named` (9,531), `unidentified` (6,028: the paper reports an impurity
  but not which phase), `none` (50,595: no impurity reported, which is not proof of purity).
- **Temperatures**: about 14% of heating temperatures in the source are in K. They are
  converted to °C; values outside 100–3000 °C are dropped (mostly heating rates tagged as K).
  `max_temp_C` is the highest heating temperature; `max_time_h` is the longest single heating
  step, with min/day units converted. Earlier tools read K as °C (9,410 reactions were
  273 degrees off).
- **Papers, not reactions**: tools group reactions by DOI. A paper reports a phase if any of
  its reactions on that route does, so a study run at five temperatures counts once.

## Tools

- **`get_literature_recipes(target)`**: for each precursor set, gives `n_reactions` and
  `n_papers`, temperature and time statistics over all its reactions, paper-level impurity
  counts, the five most-reported phases with their class, and the balanced equation.
- **`route_impurities(target, precursors, simulated_phases?, reactant_amounts?)`**: evidence
  for one route.
  - Phases are sorted into three classes, ignoring C/H/N/O when comparing elements:
    - *leftover precursor*: every element comes from one precursor (e.g. CaO from CaCO3).
    - *secondary phase*: elements come from two or more precursors.
    - *contamination*: an element that no precursor supplies (e.g. Al from a crucible).
  - Each phase gets the number of papers reporting it out of all papers on the route, a 95%
    Wilson interval, and the median maximum temperature with and without it.
  - When `simulated_phases` is given, each simulated secondary phase is labeled `confirmed`
    (≥1 paper), `rarely reported` (0 papers, upper bound < 15%), `inconclusive` (0 papers,
    too few to tell) or `no literature`. Literature secondary phases with a lower bound
    ≥ 10% that the simulation lacks are listed as `missed_by_simulation`.
  - When `reactant_amounts` is given, the mix's element ratios are checked against the
    target. Off-stoichiometry runs are still compared and reported, but flagged, with the
    balanced amounts to simulate as well. The balanced equation comes from the dataset, or
    from the balancer for routes not in the literature.
- **`check_stoichiometry(target, reactant_amounts)`**: only the ratio check, with the
  balanced equation and the balanced amounts in the caller's formula spelling.

How agents should use these tools: `skills/literature-evidence/SKILL.md`.
