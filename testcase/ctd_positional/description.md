# CTD phosphorylation by P-TEFb — positionally resolved time course (bench note)

## Why we ran this

We have measured P-TEFb acting on a CTD substrate before, by mass spectrometry on the
intact molecule. That readout tells us **how many** of the repeats carry a phosphate,
but not **which** ones, so a whole class of questions about the pattern of modification
has been out of reach.

This experiment uses a readout that resolves the individual repeats. We would like to
know what it lets us say that the old measurement could not.

## The system

RNA polymerase II carries a repetitive C-terminal domain, the CTD: tandem copies of the
seven-residue unit Tyr–Ser–Pro–Thr–Ser–Pro–Ser. In human Pol II there are 52; the
substrate here is a recombinant construct with **8 repeats**, numbered 1 to 8 from the
N-terminal end. The kinase is **P-TEFb** (CDK9–cyclin T1).

## The assay

Purified components in buffer — no DNA, no polymerase, no transcription.

- **Substrate**: 100 µM of the 8-repeat CTD construct, unphosphorylated at t = 0.
- **Kinase**: P-TEFb, catalytic, not consumed, constant throughout.
- **ATP**: 3 mM initially. Each phosphorylation consumes one ATP.
- **Sampling**: 0, 15, 30, 60, 120, 240, 480 and 960 minutes.
- **Replication**: **three independent replicates** at every time point.

Within a repeat, phosphorylation occurs on either Ser2 or Ser5 but not both at once
under these conditions, so each repeat is either modified or unmodified — one bit per
repeat, eight bits per molecule.

## What we measure, in two forms

`data/ctd_positional.csv` has one row per replicate per time point, and two blocks of
columns.

**`site1_occ` … `site8_occ` — the new part.** The fraction of substrate molecules whose
repeat *n* is phosphorylated, for each repeat in turn. This is a marginal occupancy: it
says how often each individual position is modified, across the whole population. It
does not report which positions are modified *together* in the same molecule.

**`phos0_rel` … `phos8_rel` — the old part, for continuity.** The intact-molecule signal
for CTD carrying 0, 1, … 8 phosphates, i.e. the measurement we have always had.

Two cautions on the second block. These are **relative intensities on an arbitrary
scale that drifts between injections**, so they are not comparable between time points
without a per-time-point scaling factor; you can see the nine numbers failing to sum to
a constant. And their measurement error scales with the signal. The occupancy columns in
the first block are true fractions between 0 and 1 and do not have this problem.

## What we know and what we do not

P-TEFb modifies one repeat per catalytic event and releases; earlier work using the
intact-molecule readout supported that, and nothing here is meant to revisit it.

What we cannot currently say is what sets the rate at any individual repeat, and in
particular whether the repeats are equivalent to the kinase or whether where a repeat
sits — and what has already happened around it — changes how fast it is modified. The
positional readout exists to make that answerable.

## The question

Work out what governs the rate of modification at each repeat, using both blocks of the
data. Say what the positional measurement establishes that the intact-molecule
measurement alone could not, and be explicit about anything that remains undecided even
with the new readout.
