# measurement-tech — pitfalls

---

### 1 · The loading control has usually already been divided out

**Pitfall** — Adding an offset to immunoblot data on the assumption that the background is still in there.
In most published quantifications the signal has already been normalised to a loading control
(actin, tubulin, total protein), and often to a reference lane as well.

**Why it matters** — An unnecessary offset is a free parameter that absorbs real dynamics, most visibly at
early timepoints where the model's baseline carries information. It fits better and identifies less, and
nothing downstream announces it.

**How to apply** — observation (scaling): for normalised blot data the default is a scaling factor with no offset.
Add an offset only where the description states that background was not subtracted, or where blank lanes are
reported as nonzero. assembly_verification: an offset on normalised blot data with no stated background story is a
concern.

---

### 2 · Densitometry saturates — the top of the range is censored

**Pitfall** — Treating the highest signals on a blot as ordinary measurements. Film and, at high exposure,
digital detection compress the top of the range: the true signal keeps rising and the recorded one does not.

**Why it matters** — Saturated points pull the fitted maximum down and flatten exactly the part of the
response that identifies saturation parameters and maximal rates. The residuals look like a model that
overshoots, which invites a structural move — a rate law change to fix a detector artefact.

**How to apply** — data_extraction: flag series where the top values plateau at a suspiciously common value
or where several conditions share an identical maximum. interpretation: consider censoring before
concluding the model overshoots at high dose.

---

### 3 · SD-vs-SEM mislabelling is endemic, and `n` decides it

**Pitfall** — Taking the caption at its word. In several subfields error bars are SEM by convention even
when labelled SD, and the reverse also happens; many captions state neither.

**Why it matters** — Using SEM as sigma underweights every point by a factor of √n — a silent, uniform
distortion of every likelihood weight that no downstream diagnostic reveals. The fit looks confident and the
uncertainty is wrong by a constant factor.

**How to apply** — data_extraction: record `error_type` as stated **and** flag any conflict with convention;
record `n` wherever available, since without it the SEM→SD conversion is impossible. observation (noise): with
`error_type: sem` and no `n`, estimate sigma rather than using the column. assembly_verification: an SEM column
used directly as sigma is a failed verdict.

---

### 4 · Arbitrary units mean a scaling factor, full stop

**Pitfall** — Treating a.u., "relative intensity", "fold change" or "% of control" as if the numbers had
absolute meaning, because their magnitude happens to sit near the model's.

**Why it matters** — The measurement is proportional to the model quantity by an unknown constant. Without a
scaling parameter, that constant is silently forced to 1, and the estimation compensates by distorting
whichever model parameters set the amplitude — usually total amounts and synthesis rates.

**How to apply** — data_extraction: declare `units: arbitrary` rather than guessing. observation (scaling): a
scaling factor, shared across conditions unless the experiment argues otherwise. This is also the case the
magnitude-reconciliation gate is built to catch, so a failure there usually means this entry was ignored.

---

### 5 · Replicate lanes are usually independent, not paired

**Pitfall** — Assuming replicates on a blot or plate are matched across conditions, and encoding them as
paired measurements.

**Why it matters** — Biological replicates from separate cultures on separate days share no per-replicate
effect worth pairing; treating them as paired invents structure. The reverse case — technical replicates
from one lysate treated as independent biological replicates — inflates the effective `n` and shrinks every
uncertainty statement.

**How to apply** — data_extraction: record replicate identity as it appears; flag when the description does
not distinguish technical from biological replicates, since the two carry different information and only the
description can tell them apart.

---

### 6 · Background subtraction produces genuine small negatives

**Pitfall** — Treating negative values after background subtraction as data-entry errors, and clipping them
to zero or dropping the rows.

**Why it matters** — Near-zero signal minus an estimated background is negative about half the time; that is
the noise doing its job. Clipping biases every low measurement upward, which systematically distorts
baselines and early timepoints — exactly where initial conditions and basal rates are identified.

**How to apply** — data_extraction: keep the rows, flag if you must, never drop. observation (noise): additive
normal accommodates negatives; a log transformation or a proportional noise model does not, which rules
both out for background-subtracted data.

---

### 7 · Normalisation moves the error structure with it

**Pitfall** — Applying a noise model chosen for a raw readout to data that has been divided by a control, a
loading standard or its own t=0 value.

**Why it matters** — The normaliser carries its own error, which propagates into every normalised point, and
the ratio's error is no longer the numerator's. Normalising to t=0 additionally makes the first point exact
by construction — a zero-variance measurement the likelihood will happily treat as infinitely informative if
sigma is small there.

**How to apply** — data_extraction: flag the normalisation explicitly, naming what it was normalised to.
observation (noise): state which readout the sigma refers to — raw or normalised. Consider whether the reference
point should carry data at all.

---

### 8 · A digitised figure inherits the axis, not the data

**Pitfall** — Treating points read off a published figure as equivalent to tabulated values.

**Why it matters** — Digitisation drift is systematic, not random: a misplaced axis calibration shifts or
scales an entire series, and log axes make small pixel errors into large value errors. The numbers stay
plausible, so nothing flags them, and the resulting bias is attributed to the model.

**How to apply** — data_extraction: record that a source is digitised, check the extracted range against the
figure's stated axis limits, and flag any series whose endpoints fall outside them. Cross-source
disagreement on a shared condition is a recorded finding, never resolved silently in favour of the more
convenient series.
