# Reaction templates
<!-- provenance: Jan Hasenauer, Octomod v0 agent specification (2026).
     Human-curated lineage — inherit verbatim, extend only with curated content. -->

Standard forms; prefer these over invented constructs, and name the template
used in the decision rationale.

- Synthesis: `∅ -> X` (zero-order or regulated rate)
- Degradation: `X -> ∅` (first-order unless evidence says otherwise)
- Reversible binding: `A + B <-> A_B`
- Enzymatic conversion: `S -> P` with enzyme `E` as MODIFIER
  (Michaelis-Menten when QSS holds at the declared timescale)
- Phosphorylation: `X -> X_p` with kinase as modifier
- Dephosphorylation: `X_p -> X` with phosphatase as modifier
- Transport: `X_c1 -> X_c2` (compartments explicit)
- Transcriptional activation: regulator modifies mRNA synthesis rate
- Translation: `mRNA -> mRNA + protein` (or simplified synthesis term)
- Inhibition: inhibitor enters as a MODIFIER in the rate law — never as a
  consumed reactant unless it is mechanistically consumed
- Distinct species for: compartments, PTM states, activity states,
  bound/unbound forms, complexes — whenever the distinction affects dynamics
- Preserve mass balance for metabolites and binding; when a signalling-state
  model simplifies it deliberately, SAY SO in the build report
