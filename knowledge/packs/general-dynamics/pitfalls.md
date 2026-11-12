# general-dynamics — pitfalls

---

### 1 · Bounds spanning too few decades strangle multistart

**Pitfall** — Bounds set as a tight cordon around a nominal value (half an order of magnitude either side)
look careful and are not. Multistart then samples a box that may not contain the optimum at all.

**Why it matters** — The optimiser converges tidily, the waterfall shows a clean plateau, and one or more
parameters sit against a bound. The result reads as a converged fit and is an artefact of the box. The
opposite error — ten decades on every parameter — wastes starts in regions where the model is stiff or
non-integrable and makes the integration-failure fraction the binding constraint.

**How to apply** — construction: 2–4 decades around a defensible nominal is the working default; widen where
the nominal is `default`-tier, narrow where it is measured. interpretation: a parameter at a
bound is a statement about the bound. revision_proposal: `change_bounds` is the right move only when the
bound was a guess, not when it encodes a physical limit.

---

### 2 · Rate constants belong on a log scale

**Pitfall** — Estimating rate constants on a linear scale when their plausible range spans decades.

**Why it matters** — Linear-scale sampling puts almost every start in the top decade of the range; the
lower decades are effectively unexplored. Gradients are equally distorted, and step sizes that suit one
parameter are useless for another three decades away.

**How to apply** — Rate constants, concentrations, and scaling factors are `log10`-scaled by default;
additive offsets and quantities that can legitimately be zero or negative stay `lin`. Bounds are still
written as linear-scale values — the scale field, not the bound field, carries this.

---

### 3 · The data window must bracket the dynamics you claim to estimate

**Pitfall** — Estimating a rate whose characteristic time falls outside the interval the data actually
covers: a degradation rate from data ending long before anything degrades, or a fast association from data
whose first point is at 5 min.

**Why it matters** — The parameter is not slightly uncertain, it is unconstrained, and the fit will not say
so. Whatever value the optimiser lands on is arbitrary within a wide range and will be reported with
confidence unless a profile is computed.

**How to apply** — construction: before marking a parameter for estimation, ask which part of the data
constrains it. If none, expect it in `cannot_distinguish` and consider fixing it. interpretation:
a flat profile on a rate whose timescale sits outside the data window is expected, not a surprise to explain
away.

---

### 4 · Conserved totals silently pin states

**Pitfall** — A moiety conservation the modeller did not intend — usually from writing only interconversion
reactions with no synthesis or degradation — fixes a total and therefore pins the accessible state space.

**Why it matters** — The model then cannot respond to the perturbation in the way the question asks about,
and this shows up as a stubborn misfit that invites structural moves. Meanwhile the initial values of the
conserved set become a single parameter's worth of information, so estimating them all is a structural
non-identifiability.

**How to apply** — construction: read the conservation-law advisory and confirm each class is intended. If a
total is conserved by design, estimate the total and the fractions, not every state's initial value.
interpretation: check conservation before diagnosing a missing reaction.

---

### 5 · Relative data needs one scale fixed somewhere

**Pitfall** — With arbitrary-unit data, the model's absolute concentrations and the observable's scaling
factor are only determined as a product. Estimating both freely leaves a perfectly flat direction.

**Why it matters** — The likelihood is invariant along that direction, so the optimiser wanders, profiles
run flat in both parameters, and the diagnosis reads as "the data is uninformative" when in fact the
information is there and the parameterisation is redundant.

**How to apply** — Fix one scale: a known total protein amount, an initial condition set to 1, or a scaling
factor fixed to 1 for one observable. Then say in the report that concentrations are relative to that
choice. observation (scaling) and construction must not both leave the scale free.

---

### 6 · Parameters at bounds after fitting are a finding, not a formality

**Pitfall** — Recording "converged" while one or more estimates rest on their bounds.

**Why it matters** — A parameter at a bound means the data wants a value the box forbids. Every uncertainty
statement about it is then wrong — the profile is truncated, the CI is an artefact of the box, and any
prediction depending on it inherits that. It is also the most common way a genuine model error disguises
itself as a converged fit.

**How to apply** — interpretation: name every at-bound parameter and say whether widening is
honest (the bound was a guess) or whether the model is fighting a physical limit. revision_proposal: only
the first case justifies `change_bounds`.

---

### 7 · Estimate the combination the data sees, not the pair

**Pitfall** — Estimating `k_on` and `k_off` separately when the data only ever sees equilibrium binding, or
a synthesis and a degradation rate when the data only sees the steady-state ratio.

**Why it matters** — The pair is unidentifiable but their combination (`Kd`, the steady-state level) may be
tightly determined. Reporting two flat parameters hides a sharp result; reporting them as independently
estimated values overclaims two numbers where the data supports one.

**How to apply** — construction: where binding is fast relative to the data's resolution, parameterise by
`Kd` directly. interpretation: put the pair in `cannot_distinguish` and the determined
combination in `nonetheless_determined` — both directions, in the same report.

---

### 8 · Stiffness shows up where the optimiser goes, not where you tested

**Pitfall** — A model that integrates cleanly at nominal parameters and fails across large parts of its own
bounds box.

**Why it matters** — Failed starts are dropped rather than counted, so the surviving starts form a plateau
that reads as convergence. It is survivorship: the "converged" region is simply the region where the solver
did not die, and it may exclude the optimum entirely.

**How to apply** — construction: check integrability at sampled corners of the bounds box, not just at
nominals; a denominator that can approach zero or an exponential of an unbounded expression is the usual
culprit. interpretation: read the integration-failure fraction before reading the waterfall.
