# Damped oscillator, displacement time course

Staging note for the modelling team. This case arrives as a finished PEtab
problem in `supplied/petab/`, so the construction and assembly stages are not
asked for anything — the engine enters at estimation.

- A mass on a spring is released from rest at unit displacement at t = 0 and
  allowed to ring down freely. No forcing is applied after release.
- Displacement was recorded at 50 evenly spaced times over 80 minutes.
- The readout is displacement in the same units as the initial release, so it
  is calibrated: no scaling factor belongs in the observation model.
- Noise is additive and constant across the trace; the instrument's resolution
  does not depend on the displacement.
- The quantity of interest is the natural frequency `omega`. Damping is light
  and is estimated alongside it.

**Why this case is staged.** It is here to exercise the optimiser rather than
the modelling agents. The objective is multimodal in `omega` — sampling every
1.6 min against a 3.3 min period leaves several frequencies that fit the
samples well — so a local method can converge, report a small gradient norm and
a clean fit, and still be in the wrong basin. `testcase.yaml` records the
measured landscape and a per-optimiser baseline.
