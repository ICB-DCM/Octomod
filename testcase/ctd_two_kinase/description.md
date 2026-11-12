# CTD phosphorylation by P-TEFb and by CDK7 — repeat-resolved time courses (bench note)

## Why we ran this

Our earlier measurements of P-TEFb on a CTD substrate read the intact molecule by mass
spectrometry: they tell us **how many** repeats carry a phosphate, not **which**. A
quantitative analysis of those data found that a repeat next to an already
phosphorylated repeat is modified faster, but the same analysis could not say whether
that effect runs in one direction along the array, because the readout cannot see
positions.

This experiment does two new things. It reads the individual repeats, and it puts a
second kinase on the same substrate, alone and together with P-TEFb. We want to know
what sets the rate at each repeat for each kinase, whether the local effect we inferred
before belongs to the kinase or to the substrate, and what happens when both act at
once.

## The system

RNA polymerase II carries a repetitive C-terminal domain, the CTD: tandem copies of the
heptad Tyr–Ser–Pro–Thr–Ser–Pro–Ser, 52 of them in human Pol II. The substrate here is a
**synthetic peptide of 8 consensus heptads**, numbered 1 to 8 from the N-terminal end.
The two kinases are **P-TEFb** (CDK9–cyclin T1) and the **TFIIH kinase module CDK7**
(CDK7–cyclin H–MAT1). Both are known to phosphorylate Ser5 of the consensus heptad in
vitro; CDK7 needs no prior modification of the substrate to act.

## The assay

Purified components in buffer at 30 °C — no DNA, no polymerase, no transcription.

- **Substrate**: 100 µM of the 8-repeat peptide, unphosphorylated at t = 0.
- **ATP**: 3 mM initially. Each phosphorylation consumes one ATP.
- **Kinases**: catalytic, not consumed, constant throughout. Three tubes:
  - `ptefb`: P-TEFb at 0.1 µM;
  - `cdk7`: the CDK7 module at 0.1 µM;
  - `both`: P-TEFb at 0.1 µM and the CDK7 module at 0.1 µM, added together.
- **Sampling**: 0, 15, 30, 60, 120, 240, 480 and 960 minutes.
- **Replication**: three independent replicates at every time point in every tube.

Under these conditions each repeat carries at most one phosphate: both kinases place it
on Ser5 of this consensus construct, and we do not observe repeats carrying two. So a
repeat is either modified or unmodified — one bit per repeat, eight bits per molecule,
whichever kinase did the modifying. The readout does not tell us which kinase placed a
given phosphate.

## How the repeats are told apart

A consensus construct gives the same peptide from every repeat, so a digest on its own
cannot say which repeat a phosphopeptide came from. To make the repeats distinguishable
without changing the sequence, each heptad of the synthetic peptide was built with its
own pattern of stable-isotope-labelled residues (heavy carbon and nitrogen on proline and
tyrosine), so that every heptad has a unique mass. The peptide is wild type in sequence;
only the isotopes differ. After quenching, the sample is digested with chymotrypsin,
which cleaves after tyrosine and releases heptad-length peptides, and the digest is run
by LC–MS/MS with UV photodissociation, which keeps the phosphate on the fragment and
localises it to the residue.

## What we measure, in two forms

`data/ctd_two_kinase.csv` has one row per replicate per time point per tube, a
`condition` column naming the tube, and two blocks of columns.

**`site1_occ` … `site8_occ` — the repeat-resolved part.** For each repeat, the fraction
of substrate molecules on which that repeat is phosphorylated, taken as the ratio of the
phosphorylated to the summed phosphorylated and unmodified signal of that repeat's
peptide within one run. Being a ratio within a run, it needs no scale factor and lies
between 0 and 1 up to noise. It is a marginal occupancy: it says how often each position
is modified across the population, not which positions are modified together in one
molecule.

**`phos0_rel` … `phos8_rel` — the intact-molecule part, for continuity.** The intact
peptide's signal for molecules carrying 0, 1, … 8 phosphates, from the same samples
before digestion: the measurement we have always had.

Two cautions on the second block. These are **relative intensities on an arbitrary scale
that drifts between injections**, so they are not comparable between time points
without a per-time-point scaling factor; you can see the nine numbers failing to sum to
a constant. Their error scales with the signal. The occupancy columns do not have either
problem; their error is a small additive scatter of the ratio.

## What we know and what we do not

P-TEFb modifies one repeat per catalytic event and releases; the earlier intact-molecule
work supported that, and the quantitative analysis of it found the local effect
described above, without being able to settle its direction. Nothing here is meant to
revisit the distributive mode.

For CDK7 on this substrate we have no prior kinetic characterisation at all: whether its
rate at a repeat depends on what has already happened around that repeat, or on where the
repeat sits, is not known.
Nor has anyone put the two kinases on one substrate at the same time and read the
result, so we do not know whether their activities simply add.

## The question

Work out what governs the rate of modification at each repeat for each kinase, using
both blocks of the data from the single-kinase tubes. Say whether the local effect of
P-TEFb has a direction along the array, and whether it is a property of the kinase or
of the substrate, using CDK7 on the same substrate as the comparison. Then say what the
model predicts for the tube with both kinases, and be explicit about anything that
remains undecided even with the repeat-resolved readout.
