# Phospho-R time course, synthetic receptor module

Lab note as handed to the modelling team. Densitometry table is in
`data/timecourse.csv`.

- Cells expressing the synthetic receptor module were serum-starved overnight and
  held in the same buffer for the whole experiment.
- Ligand was added at t = 0. Three relative dose levels were used: 0.3, 1 and 3.
  These are relative to our standard working stock; we have no absolute
  concentration for the ligand preparation.
- Lysates were collected at 0, 5, 10, 20, 40 and 60 min after addition.
- Phospho-R was quantified by immunoblot densitometry against a phospho-specific
  antibody. The reported column `pR_au` is background-subtracted band intensity
  in arbitrary densitometry units — it is not calibrated against any standard,
  so only relative comparisons within this dataset are meaningful.
- Total R was blotted in parallel on the same lysates and was flat across all
  doses and timepoints at roughly 10 normalised units. We see no evidence of
  receptor synthesis or degradation over this one-hour window.
- The t = 0 samples are unstimulated cells collected immediately before ligand
  addition. Phospho-R is at or near zero in those lanes.
- Each dose/time point was run as two independent lanes from separate wells
  (`replicate` 1 and 2). They are biological replicates, not technical repeats
  of the same lysate.
- We have not supplied an error column. Use the replicates.
- Some early-time densitometry values came out slightly below zero after
  background subtraction. That is the background model, not a negative signal;
  we have left the numbers as measured rather than flooring them at zero.
- Question for the modelling side: does the dose response look like what you
  would expect from this module, and once you have calibrated on the lower
  doses, can you predict the top dose?
