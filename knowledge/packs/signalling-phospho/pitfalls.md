# signalling-phospho — pitfalls

---

### 1 · Phospho-states of one protein share a conserved total

**Pitfall** — Modelling unphosphorylated and phosphorylated forms as independent pools with separate
synthesis and degradation, rather than as states of one protein whose total is conserved over the
experiment.

**Why it matters** — Independent pools let the model produce phospho-protein without depleting the
substrate, so the dynamics have a degree of freedom the biology does not have — most visibly at saturating
dose, where the real system runs out of substrate and the model does not. It also silently doubles the
initial conditions to be estimated when the data determines only their sum.

**How to apply** — construction: write interconversion reactions (`R -> Rp`, `Rp -> R`) and estimate the
total plus the basal fraction, not each state's initial value independently. Confirm the conservation
advisory reports the class you intended. observation (mapping): a "total protein" readout is the sum of all
states, including bound and multiply-phosphorylated ones.

---

### 2 · Basal phosphorylation is rarely exactly zero

**Pitfall** — Setting the phosphorylated state's initial value to 0 because the experiment starts before
stimulation.

**Why it matters** — Constitutive kinase and phosphatase activity leaves a nonzero steady-state basal level
in most unstarved cells, and blots usually show it. Forcing zero at t=0 makes the model start below the data
and puts a systematic positive residual on every early point — which reads as a missing fast process and
invites a structural move that fixes nothing.

**How to apply** — construction: give the phospho-state a basal initial value, ideally as the steady state
of the unstimulated system rather than a free parameter. condition: serum starvation is the
condition where near-zero basal is defensible — and it is also the case for pre-equilibration (given in
full, e.g. `preequilibration: {"S": 0}`), since overnight starvation is exactly a settled baseline. interpretation: a uniform early-time offset
is this entry before it is a missing reaction.

---

### 3 · Signalling is minutes; expression is hours

**Pitfall** — Including protein synthesis and degradation as estimated parameters in a model fitted to a
time course shorter than about an hour.

**Why it matters** — Over that window total protein levels do not measurably change, so synthesis and
degradation are unconstrained. They will nevertheless take values, absorb misfit that belongs to the
signalling dynamics, and appear in the report as estimated quantities the data says nothing about.

**How to apply** — construction: on sub-hour data, fix synthesis and degradation to zero (or to a balanced
pair holding the total constant) and record the timescale argument in the build report. On multi-hour data
they become genuinely estimable and transcriptional feedback may need representing at all.
interpretation: expect them in `cannot_distinguish` if they were left free.

---

### 4 · Dose enters through occupancy, and occupancy saturates

**Pitfall** — Encoding ligand dose as a quantity that enters the rate law linearly, so that ten times the
dose gives ten times the input.

**Why it matters** — Receptor binding saturates. Across a dose range chosen to span the response — which is
what experimentalists choose — the top doses are near-saturating by design. A linear input then forces the
model to over-respond at high dose, and the misfit grows with dose in a pattern easily misread as a wrong
downstream rate law.

**How to apply** — construction: represent the input as occupancy (an explicit binding step, or a saturating
function of dose) unless every dose is demonstrably in the linear regime. condition: override the
ligand concentration, not the downstream activation rate, so the saturation stays in the model.
revision_proposal: dose-scaling misfit points at `change_kinetic_law` on the input step before anything
deeper.

---

### 5 · A "phospho-X" antibody may not mean one site

**Pitfall** — Mapping a phospho-specific readout to a single model state when the protein carries several
phosphorylation sites.

**Why it matters** — Antibodies raised against one phospho-site frequently detect related sites or
neighbouring epitopes, and many published readouts are effectively "phosphorylated somewhere in this
region". Mapping such a readout to one state understates the measured pool and biases the parameters
governing that specific site — invisibly, since the fit can compensate through the scaling factor.

**How to apply** — observation (mapping): where the model has multiple phospho-forms, state which the antibody is
claimed to detect and at what evidence tier; if the source does not say, map to the sum and record the
uncertainty rather than choosing. assembly_verification: a single-state mapping in a multi-site model with no
stated specificity evidence is worth a concern.

---

### 6 · Overshoot-then-decline is feedback, not a rate constant

**Pitfall** — Fitting a transient peak followed by a decline to sub-peak levels with a model that has no
negative feedback or receptor removal, by driving deactivation rates upward.

**Why it matters** — A model without feedback can produce a peak only through substrate depletion, so the
optimiser buys the shape at the cost of an implausible deactivation rate, and the peak's height and timing
end up coupled in a way the real system does not have. Predictions at unmeasured doses then fail even though
the training fit looks fine — which is what held-out conditions exist to catch.

**How to apply** — interpretation: a peak the model cannot reach, or reaches at the wrong time,
with a deactivation rate at its upper bound, is this entry. Candidate mechanisms — receptor internalisation,
induced phosphatase, inhibitory phosphorylation — are usually not distinguishable from the timecourse alone,
so rank them and say so rather than naming one.

---

### 7 · Stimulation is not instantaneous

**Pitfall** — Encoding stimulus as a step change at t=0 when the data's earliest points show a lag before
anything moves.

**Why it matters** — Ligand addition, mixing, binding and the first steps of the cascade take time that a
step input assigns to zero. The model then rises too early, and the residual pattern — negative early,
positive later — is the classic signature that gets diagnosed as a wrong rate constant. Compensating through
rate constants distorts the whole cascade's timing.

**How to apply** — construction: if the first measured points are flat, represent the intervening steps
explicitly (binding, an intermediate) rather than tuning rates to imitate a delay.
interpretation: sign runs early-then-late across every condition point at a missing delay before
they point at a rate constant.
