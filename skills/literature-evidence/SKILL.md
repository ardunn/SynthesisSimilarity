---
name: literature-evidence
description: Use the synthesis-similarity MCP tools to propose precursors from the text-mined solid-state literature, look up reported recipes and conditions, check a simulated route's impurity phases against literature, and check a simulation recipe's precursor ratios. Use whenever a question needs literature precedent, heating conditions, impurity phases, or a stoichiometry check for a solid-state synthesis.
---

# Literature evidence for solid-state synthesis

Backed by Lee et al., *Sci. Data* 2025: 66,154 text-mined reactions from 46,816 papers
(see `LITERATURE_DB.md`). Formulas are matched on normalized composition, so
`Li2CO3` and `CO3Li2` are the same material.

## Which tool

| Question | Tool |
|---|---|
| What precursors should I use for X? | `recommend_precursors(target)` |
| X is novel; what is it like? | `find_similar_materials(formula)`, then `get_literature_recipes` on a neighbor |
| How has X been made, at what temperatures, with what impurities? | `get_literature_recipes(target)` |
| Did this simulated route's impurities show up in the literature? | `route_impurities(target, precursors, simulated_phases, reactant_amounts)` |
| Is this recipe's ratio right for the target? | `check_stoichiometry(target, reactant_amounts)` |
| Is this precursor set possible at all? | `balance_reaction(target, precursors)` |
| Some precursors are fixed; what completes the set? | `complete_precursor_set(target, fixed_precursors)` |

## Checking a ReactCA (or other) simulation

1. **Ratio first.** Call `check_stoichiometry` with the exact amounts that were simulated.
   If the status is `off_stoichiometry`, the run still counts. Report it, flagged with the
   limiting element and the excess, and **also simulate `balanced_reactant_amounts`**.
   Present the two runs as a pair, since the difference shows the ratio's effect.
2. **Impurities.** Pass every non-target phase above about 1 wt% as `simulated_phases`, and
   the simulated amounts as `reactant_amounts`, to `route_impurities`.
3. **Read the result by class.** Phases are classed by their elements, ignoring C/H/N/O:
   - **secondary phase** (elements from two or more precursors, e.g. Li2SiO3): a competing
     phase. Labels:
     - `confirmed`: at least one paper on the route reports it.
     - `inconclusive`: no paper reports it, but there are too few papers to say more.
     - `rarely reported`: no paper reports it and the interval's upper bound is below 15%.
     - `no literature`: no papers on this route.
     - `missed_by_simulation`: commonly reported in literature, but absent from the
       simulation.
   - **leftover precursor** (unreacted or decomposed precursor, e.g. CaO from CaCO3):
     incomplete conversion. Its paper count shows how often real syntheses stop there.
   - **contamination** (an element no precursor supplies, e.g. Al from a crucible): not
     something a simulation should reproduce.
4. **Quote counts, not adjectives.** Say "12 of 53 papers (CI 13–36%)", not "commonly".
   `median_max_heating_C` (with vs without the phase) shows whether a phase belongs to low-
   or high-temperature runs. Li2SiO3 on the Li4SiO4 route, at 800 vs 925 °C, is an
   intermediate of incomplete reaction.

## Caveats

- **"None reported" is not proof of purity.** The extraction's impurity F1 is about 0.88,
  and papers under-report minor phases. Treat 0 papers as weak evidence unless there are
  many papers on the route.
- **Counts are papers (distinct DOIs), not reactions.** A five-temperature study counts once.
- **Literature equations describe balanced reactions,** not the amounts each paper actually
  weighed out.
- **Temperatures are °C.** Source values in K are converted, and implausible values are
  dropped.
