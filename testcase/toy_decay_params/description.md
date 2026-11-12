# Reporter A decay after synthesis shutoff

Lab note as handed to the modelling team. Plate reader table is in
`data/decay.csv`.

- Cells carry a fluorescent reporter, A, under an inducible promoter.
- Synthesis was shut off at t = 0 by washout. Everything before t = 0 is
  steady-state expression under induction; the experiment starts at the moment
  of washout.
- Fluorescence was read at 0, 0.5, 1, 2, 3, 5, 7 and 10 h after shutoff.
- The instrument was calibrated against a purified protein dilution series run on
  the same plate, so the reported column `A_conc` is on an approximately absolute
  concentration scale. These are not arbitrary units — a value of 5 means the
  same thing at t = 0 as it does at t = 10 h, and the same thing in both wells.
- Starting levels sit somewhere around 8 to 12 on that scale; induction strength
  varies a little between preparations and we have not normalised it out.
- Two independent wells were followed (`replicate` 1 and 2), seeded from separate
  overnight cultures.
- No error column is supplied; the two wells are the error estimate.
- Cells were held at low density in stationary phase for the duration, so there is
  no appreciable growth dilution over the 10 h window. Loss of signal is
  degradation of the reporter.
- Background fluorescence from untransfected wells was subtracted during
  calibration and was small relative to the signal at all timepoints.
- Question for the modelling side: what is the degradation rate constant of A, and
  how well is it pinned down by this dataset?
