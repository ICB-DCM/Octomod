# CTD phosphorylation by P-TEFb — intact-molecule time course (bench note)

## The system

RNA polymerase II carries a repetitive C-terminal domain, the CTD: tandem copies of the
seven-residue unit Tyr–Ser–Pro–Thr–Ser–Pro–Ser. In human Pol II there are 52; the
substrate here is a recombinant construct with **8 repeats**. The kinase is **P-TEFb**
(CDK9–cyclin T1).

## The assay

Purified components in buffer — no DNA, no polymerase, no transcription.

- **Substrate**: 100 µM of the 8-repeat CTD construct, unphosphorylated at t = 0.
- **Kinase**: P-TEFb, catalytic, not consumed, constant throughout.
- **ATP**: 3 mM initially. Each phosphorylation consumes one ATP.
- **Sampling**: 0, 15, 30, 60, 120, 240, 480 and 960 minutes.
- **Replication**: three independent replicates at every time point.

Within a repeat, phosphorylation occurs on either Ser2 or Ser5 but not both at once
under these conditions, so each repeat is either modified or unmodified — one bit per
repeat, eight bits per molecule.

## What we measure

Mass spectrometry on the **intact** substrate molecule. Each phosphate adds a fixed
mass, so the spectrum separates molecules by **how many** of the eight repeats carry a
phosphate — a number from 0 to 8.

**It does not resolve which repeats those are.** A molecule modified on repeats 1 and 2
and one modified on repeats 1 and 7 have the same mass and fall in the same peak. The
data are nine numbers per replicate per time point, and the arrangement behind them is
not observed.

`data/ctd_countonly.csv` holds them as `phos0_rel` … `phos8_rel`. Two cautions. They are
**relative intensities on an arbitrary scale that drifts between injections**, so they
are not comparable between time points without a per-time-point scaling factor — the
nine numbers do not sum to a constant. And their measurement error scales with the
signal rather than being constant in absolute terms.

## What we know and what we do not

P-TEFb modifies one repeat per catalytic event and releases, and earlier work with this
kind of readout supported that. What we cannot currently say is what sets the rate at
any individual repeat, and whether the repeats are equivalent to the kinase or whether
what has already happened around a repeat changes how fast it is modified.

## The question

Work out what governs the rate of modification at each repeat. Be explicit about what
this measurement can and cannot establish — we would much rather be told that a question
is beyond this data than be given an answer the data do not support.
