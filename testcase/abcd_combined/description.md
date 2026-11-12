# SynMod-4 induction time course

Lab note as handed to the modelling team. Data table is in
`data/synmod4_ms.csv`.

- SynMod-4 is an engineered four-protein module we carry in *S. cerevisiae*. It
  was assembled from synthetic parts and has no host homologues, so there is no
  literature on it beyond our own construction notes.
- The parts, as designed: an inducer activates the kinase **KinA**; active KinA
  is required to activate the regulator **RegB**; and the inert precursor
  **PreC** is converted into the product **ProD**.
- Inducer was added at t = 0 and kept in the medium for the whole run. Dose `u`
  is in relative units against our standard stock; three levels were used, 0.25,
  1 and 4.
- Some cultures were pre-treated with **BX-11**, a commercial inhibitor that
  blocks RegB activation specifically. In vitro it removes more than 90% of RegB
  activation at the concentration we use, with no measurable effect on KinA in
  the same assay. Column `bx11` is 1 for treated cultures, 0 for untreated.
- Samples were taken at 0, 5, 15, 30, 50, 75, 100 and 120 min (`time_min`).
- Readout is targeted MS on whole-cell lysates, calibrated against heavy-labelled
  peptide standards, so all three measurement columns are absolute
  concentrations in uM rather than arbitrary units. `KinA_p_uM` and `RegB_p_uM`
  are the active (phosphorylated) forms; `ProD_uM` is the product.
- Two independent cultures per dose/time point (`replicate` 1 and 2), grown from
  separate transformants on separate days — biological, not technical, repeats.
  We have not supplied an error column; use the replicates.
- KinA and RegB are expressed from calibrated constitutive promoters. We blotted
  total KinA and total RegB separately: both are flat over this window, and we
  report the active forms against a total normalised to 1 for each. The
  PreC + ProD pool is about 5 uM in total and likewise does not change
  appreciably over two hours.
- ProD is lost slowly by a mix of turnover and dilution. We cannot separate the
  two and have not tried to.
- The t = 0 samples are uninduced cells harvested immediately before the inducer
  went in. All three species sit at or near zero there.
- A few early-time values came out slightly below zero. That is the standard
  curve subtraction, not a negative concentration; we have left the numbers as
  measured rather than flooring them.

That is what we have. The module is described above as we designed and built it;
the numbers in data/ are what came out of the assay. We are handing this over
without a list of our own doubts attached, because we would rather hear what the
data says than have you check the boxes we happen to be worried about.
