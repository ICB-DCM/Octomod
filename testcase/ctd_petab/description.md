# CTD phosphorylation by P-TEFb — a supplied model to be calibrated

A complete PEtab problem is supplied in `supplied/petab/`: the model, the
measurements, the observables, the conditions and the parameter table. The model
structure is not in question here and is not to be revised. What is wanted is a
calibration of it, and an honest account of what these measurements can and cannot
pin down.

## The system, in brief

RNA polymerase II carries a repetitive C-terminal domain of seven-residue units. The
substrate here is a construct with 8 such repeats, each either phosphorylated or not,
giving 256 possible configurations. The kinase P-TEFb adds one phosphate per catalytic
event, consuming one ATP; it is catalytic and its concentration does not change.
Substrate is 100 µM, ATP 3 mM.

## The measurements

Mass spectrometry on the intact molecule, at 0, 60, 120 and 960 minutes. It resolves
how many of the eight repeats carry a phosphate — a number from 0 to 8 — but not which
ones. Nine numbers per time point, thirty-six in total, one condition.

The measured quantities are relative signal intensities on a scale that drifts between
injections, so the model includes scaling parameters that map predicted amounts onto
measured intensities, with a separate factor per time point. Those scaling parameters
are estimated from the same data as the kinetic ones, and they are part of the answer.

## What is wanted

Fit the supplied problem. Report every estimated parameter with an interval. Say
plainly which parameters these thirty-six measurements determine and which they do not,
and show the evidence for convergence rather than asserting it.
