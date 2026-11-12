# Communication between immune cell populations in one well of stimulated human blood cells — a mass-cytometry time course (lab note)

This note describes an experiment we did not perform ourselves: we re-analysed
the single-cell files deposited by Bodenmiller et al., *Nat Biotechnol* 30:858
(2012), for one of their experiments, a stimulation time course on peripheral
blood mononuclear cells. Everything about the cells, the plate and the
measurement is theirs; the gating, the per-population summaries and the noise
model are ours and are described here. The question we bring to the data is
ours too, and it is not the one the paper asked.

## The system

Peripheral blood mononuclear cells (PBMCs) from **one healthy human donor**: a
mixture of T cells, B cells, natural killer (NK) cells, monocytes and dendritic
cells, thawed and kept as a suspension in culture medium. Each well of the plate
holds the whole mixture. The point that matters for this note: **all the
populations of a well share one medium**, so anything one population secretes
into the well reaches every other population in it within minutes.

The pathway we read out is cytokine receptor → receptor-associated JAK kinases →
tyrosine phosphorylation of STAT transcription factors. The readouts are
**STAT1 pY701**, **STAT3 pY705** and **STAT5 pY694** (antibody clones 4a, 4, 47),
measured per cell and summarised per population. Total protein levels were
**not** measured.

Seven stimulation conditions are staged, every one for all five populations:
IFN-α, IFN-γ, LPS, GM-CSF, G-CSF, IL-3, and a Reference well with no stimulus.
Which populations respond to each stimulus directly is part of what the data
have to say.

## The experiment (from the authors' Online Methods and Supplementary Methods)

- PBMCs were thawed from cryostorage, washed and rested at 37 °C, distributed
  **once** into the 96 wells of a 2-ml deep-well block (~200,000 cells in
  ~200 µl per well), and rested 60 min before stimulation. The methods describe
  a 1-h incubation after thawing and a 60-min rest after aliquoting; whether
  these are one rest or two is not stated, so the cells rested 1–2 h in total.
- **One 96-well plate is the whole experiment.** Column = stimulus, row = time
  between adding the stimulus and fixing the cells. Plate map from the authors'
  Supplementary Methods, Table 2: columns 1–12 = sodium orthovanadate, IL-2,
  IL-3, IL-12, Reference, G-CSF, GM-CSF, BCR/FcR-XL, IFN-γ, IFN-α, LPS,
  PMA/ionomycin; rows A–H = 0, 1, 5, 15, 30, 60, 120, 240 min. The staged
  columns are 3, 5, 6, 7, 9, 10 and 11.
- Doses: every cytokine **and LPS at 30 ng/ml**. Stimuli stayed in the medium;
  nothing was washed out, and nothing was added later.
- At its time point each well was **fixed in place** (formaldehyde 1.6 %,
  10 min), permeabilised in methanol and stored at −80 °C. Fixation stops all
  signalling; each well is a snapshot of one incubation duration. The **0-min
  row was fixed immediately after the stimulus was added**, so its 12 wells
  are, in effect, 12 unstimulated replicates.
- Each well was labelled with a unique 7-metal barcode, **all 96 wells were
  pooled into a single tube**, stained once with the full antibody panel and
  measured in **one run** on a CyTOF mass cytometer. Consequence: staining and
  instrument conditions are identical for all wells and all cell types. Any
  difference between wells arose in the well, before fixation.
- 35 channels per cell: 10 surface markers (CD3, CD4, CD7, CD14, CD20, CD33,
  CD45, CD123, IgM, HLA-DR), 14 phosphorylation sites, 7 barcode channels, 2
  DNA channels, time and cell length. No phospho-JAK, no total-protein channel,
  no viability stain, no cytokine measurement of the medium.

## What the numbers are

The deposited files (Cytobank experiment 15711) hold 718,075 cells across the
96 wells. Per cell and channel the instrument reports a bead-normalised ion
count; small negative values at the low end are an instrument property.

Our processing:

1. **Transform**: arcsinh(x/5) on every channel. **All values in the table are
   on this scale.** For counts well above ~10 a difference of 1.0 is a factor
   2.7; near zero the scale is close to linear, so the B- and NK-cell pSTAT1
   baseline of ~1.0 (≈ 6 counts) is near the instrument floor and the monocyte
   baseline of ~4.0 (≈ 136 counts) is not "e³ times more". The values are
   relative intensities, not molecule numbers; the same antibody and instrument
   apply to every cell type, so the mapping from phosphorylated protein to
   signal is shared across populations, but its absolute scale is unknown.
2. **Cell populations** along the paper's Fig. 4c tree, each cut-off at the
   density minimum of our pooled data within its parent population (the
   authors used clustering and published no cut-offs):

   | population | rule (Fig. 4c) | mean % of cells | typical cells per well |
   |---|---|---|---|
   | `Tcell_CD4` | CD20− IgM− CD7+ CD3+ CD33− CD4+ | 26.6 | 2,100 |
   | `Tcell_CD4neg` | CD20− IgM− CD7+ CD3+ CD33− CD4− (no CD8 antibody; the authors call this "CD8+ T") | 13.4 | 1,000 |
   | `Bcell` | CD20+ CD3− | 10.2 | 800 |
   | `NKcell` | CD20− IgM− CD7+ CD3− CD33− CD4− (no CD56/CD16 in the panel) | 24.5 | 1,900 |
   | `Monocyte` | CD20− IgM− CD7− CD3− CD33+ CD14+ | 14.1 | 1,700 at 0 min, 76–520 at 240 min |

   Cut-offs (arcsinh scale): CD20 2.28, CD3 1.58, IgM 2.03, CD7 2.13; within
   CD7+ cells CD3 1.18 and CD33 1.98; CD4 1.43 within T cells and 1.58 within
   CD7+ CD3− cells; CD33 1.48 within CD7− cells; CD14 1.38 within CD33+ cells.
   In the staged wells the five gates cover 87–93 % of the events; the rest are
   CD14− monocytes, CD123+ cells, surface-negative cells and cells the tree
   leaves out, such as CD7− T cells. Dendritic cells are not staged.
3. **Summary statistic**: the **median** over the cells per well, population
   and phospho-site. It describes a uniform population shift well; where only
   part of a population responds the median understates the responders.

## The data file

`data/pbmc_well_jakstat_timecourse.csv` — 840 rows: 7 stimuli × 8 times × 15
readouts. It is a slice of our full table (12 stimuli × 8 times × 5 populations
× 14 phospho-sites, 6,720 rows).

**The readout label carries the population.** A readout is one phospho-site in
one population, `pStat1_Bcell`, `pStat3_Monocyte` and so on, fifteen in all.
There is no population column: the five populations of a well were measured
together in one sample, and this file presents them that way, as fifteen
quantities read from one well at one time. A condition is a stimulus, nothing
else.

| column | meaning |
|---|---|
| `stimulus` | `IFN-a`, `IFN-g`, `LPS`, `GM-CSF`, `G-CSF`, `IL-3`, or `Reference` |
| `time_min` | minutes between stimulus addition and fixation: 0, 1, 5, 15, 30, 60, 120, 240 |
| `readout` | `<site>_<population>`: site `pStat1`, `pStat3` or `pStat5`; population `Tcell_CD4`, `Tcell_CD4neg`, `Bcell`, `NKcell` or `Monocyte` |
| `median` | the measurement: median arcsinh(count/5) over the cells of that population in that well. **Never edited.** |
| `n_cells` | cells behind that median |
| `well` | plate position |
| `sigma_bw` | well-to-well reproducibility of a median for this readout, from the unstimulated 0-min wells |
| `se_median` | sampling error of the median from finite cells, 1.2533·SD/√n |
| `sigma_unwidened` | √(σ_bw² + se_median²) |
| `sigma_widening` | 1.0 everywhere except 2.0 on the 42 monocyte rows at 120 and 240 min |
| `sigma` | `sigma_unwidened × sigma_widening` — **the noise model to use**, fixed, per row |

**Noise.** There is one well per (stimulus, time), so no replicate wells exist
except the 0-min row (11 usable wells; the orthovanadate well is excluded
because pervanadate acts within seconds). From those we estimate the
well-to-well component σ_bw per readout. Typical total σ is 0.02–0.06 in
lymphocytes and 0.04–0.09 in monocytes, up to 0.2 in the thinnest late monocyte
wells before widening, against responses of 0.5–2.3 units. Within-well
cell-to-cell spread (SD 0.5–1.1) is biological heterogeneity, not measurement
error, and is not in this table. **We recommend the fixed `sigma` column, not a
fitted σ.**

**Why the monocyte σ at 120 and 240 min is widened.** The monocyte gate loses
cells over the 4 h, and loses them faster under stimulation. Cells in the
monocyte gate at 240 min: 520 in the Reference well, 422 under GM-CSF, 409 under
IL-3, 296 under IFN-γ, 249 under G-CSF, 115 under IFN-α and 76 under LPS,
against about 1,700 at 0 min. The monocytes still measured at 120 and 240 min
are a remainder, a selected subset whose signalling state may differ from the
cells that were lost, and under LPS and IFN-α a small one. No error bar
captures that selection. We widen σ on those 42 rows by a factor 2 as a
declared judgement of the study team (§Decisions, item 5); the unwidened value
and both of its components stay in the file so anyone can undo it.

## The 0-min row is shared, and the basal level is not zero

All 105 series start from the same unstimulated state after 1–2 h of rest in
medium. Basal phosphorylation differs by population: pSTAT1 sits at ~4.0 in
monocytes, 2.3 in T cells, 1.0 in B and NK cells; pSTAT3 and pSTAT5 at ~1.0 in
monocytes and 0.2–0.4 in lymphocytes. In 11 of the 14 phospho-channels the
monocyte 0-min median lies 0.5–1.6 units above the lymphocyte mean; pSTAT1 is
the largest gap at 2.3, and pS6 (+0.1) and pLat (−0.4) are the exceptions. We
therefore give each readout its own constant **background count** (§Decisions,
item 2), with a possible real constitutive component on top that these data
cannot separate from it.

## What we saw in the data

Δ is the stimulated median minus the Reference median **at the same time**, in
arcsinh units, so the drift of the unstimulated wells (next section) is
subtracted. Every staged series is listed, so that silence in this note is never
read as a null result.

**The direct responses.** After IFN-α all three STATs rise within 5 min in every
population and peak at 15–30 min, then decline at different rates in the same
cells: in both T-cell populations pSTAT5 is back near Reference by 240 min while
pSTAT3 remains highest; in B and NK cells pSTAT1 persists while pSTAT3 and
pSTAT5 fall; in monocytes all three are back at or below Reference by 60–240 min.
After IFN-γ, monocytes respond on all three STATs and pSTAT1 stays at half its
peak for 4 h; B cells respond on pSTAT1 only, sustained; CD4 T cells weakly on
pSTAT1; **CD4-negative T cells and NK cells do not respond to IFN-γ at all**
(Δ within 0.05 at every time), although the same gates respond strongly to
IFN-α. In monocytes GM-CSF, G-CSF and IL-3 raise pSTAT5 to +2.1–2.3 at 15 min,
about twice the interferon peaks, fall steeply between 30 and 60 min and settle
at +0.3 to +0.5 above Reference for the rest of the 4 h; G-CSF also
phosphorylates STAT3 in monocytes (+1.19 at 15 min); none of the three
phosphorylates STAT1. Under LPS the monocytes respond on the non-STAT channels
of the panel (pNF-κB +0.4, pp38 +1.6, pErk +1.6 above Reference at 15 min) and,
on the STATs, only weakly and late (pSTAT1 +0.12 and +0.18 at 120 and 240 min);
their pSTAT3 and pSTAT5 under LPS end below the Reference well, with the caveat
on the late monocyte rows above.

**The late responses in the lymphocytes.** This is the observation the question
is about.

| population | readout | LPS: Δ at 15 / 120 / 240 min | IFN-α: Δ at 15 / 120 / 240 min |
|---|---|---|---|
| `Tcell_CD4` | pStat1 | −0.03 / +0.52 / +0.50 | +1.26 / +0.55 / +0.41 |
| `Tcell_CD4` | pStat3 | +0.01 / **+1.33** / +0.83 | +1.57 / +1.35 / +0.85 |
| `Tcell_CD4` | pStat5 | −0.03 / +0.49 / +0.24 | +1.90 / +0.56 / +0.17 |
| `Tcell_CD4neg` | pStat1 | +0.03 / +0.28 / +0.22 | +1.02 / +0.30 / +0.28 |
| `Tcell_CD4neg` | pStat3 | +0.01 / +0.40 / +0.44 | +1.40 / +0.46 / +0.49 |
| `Tcell_CD4neg` | pStat5 | +0.02 / +0.30 / +0.02 | +1.38 / +0.27 / +0.04 |
| `Bcell` | pStat1 | −0.05 / **+0.73** / **+0.95** | +1.16 / +0.92 / +1.04 |
| `Bcell` | pStat3 | +0.04 / +0.20 / +0.26 | +0.97 / +0.51 / +0.44 |
| `Bcell` | pStat5 | +0.01 / +0.04 / +0.05 | +0.65 / +0.20 / +0.08 |
| `NKcell` | pStat1 | +0.05 / **+0.77** / +0.60 | +1.09 / +0.78 / +0.74 |
| `NKcell` | pStat3 | 0.00 / +0.21 / +0.12 | +0.82 / +0.30 / +0.19 |
| `NKcell` | pStat5 | +0.01 / +0.01 / +0.22 | +0.24 / +0.13 / +0.12 |

In words: under LPS nothing happens in any lymphocyte population for the first
hour (|Δ| ≤ 0.05 at 1, 5, 15 and 30 min, and ≤ 0.1 at 60 min). Between 60 and
120 min every lymphocyte population starts to respond: a large pSTAT3 rise in
CD4 T cells, a pSTAT1 rise in B and NK cells, and smaller mixed rises in the
other T cells. Population by population and STAT by STAT, the late LPS values
at 120 and 240 min lie close to the same population's own response to added
IFN-α at the same times, about 100 min after that response began. The one place
the match is loose is B cells, where the late LPS response is more STAT1-only
than the IFN-α response at 120 min.

The colony-stimulating factors show a late response of a different shape. At
240 min CD4 T cells show a pSTAT3 rise under G-CSF (+0.87), GM-CSF (+0.50) and
IL-3 (+0.21), the CD4-negative T cells a smaller one (+0.20, +0.06, +0.09),
while **B and NK cells show no late pSTAT1 rise under any of the three**
(+0.12 / +0.13 at most). So the late STAT3 response in T cells appears under LPS
and under all three colony-stimulating factors, and the late STAT1 response in
B and NK cells under LPS only.

Two further observations belong to the same picture. Under IFN-α itself, CD4 T
pSTAT3 falls from its peak to 1.35 at 60 min and rises again to 1.63 at 120 min
(Reference 0.28), a second wave the direct response does not obviously
explain. And under IFN-γ, CD4 T pSTAT3 climbs slowly from 60 min to +0.35 at
240 min in cells whose pSTAT1 response to IFN-γ is weak.

## The Reference column is not flat, and the drift is large in monocytes

Over 4 h in the plate the unstimulated cells change. The Reference at 240 min,
relative to the mean of the 11 unstimulated 0-min wells, in units of that
row's σ before widening:

| population | pSTAT1 | pSTAT3 | pSTAT5 |
|---|---|---|---|
| `Tcell_CD4` | +0.12 (3 σ) | +0.24 (11 σ) | +0.16 (6 σ) |
| `Tcell_CD4neg` | +0.37 (10 σ) | +0.17 (7 σ) | +0.23 (9 σ) |
| `Bcell` | +0.11 (2 σ) | +0.18 (4 σ) | +0.15 (4 σ) |
| `NKcell` | +0.35 (7 σ) | +0.26 (9 σ) | +0.35 (12 σ) |
| `Monocyte` | +0.29 (3 σ) | **+0.93 (19 σ)** | **+0.81 (14 σ)** |

The drift is mostly a slow rise after 60 min. It is not a staining or
instrument artefact (all wells were stained and measured together), so it
happened in the wells. Other channels drift too: in every population pErk,
pPlcg2 and pSlp76 rise and pS6 falls; monocytes additionally gain pNF-κB and
pp38 and lose pAkt. The drift is also an observation: a slow rise of pSTAT3 and
pSTAT5 in every population of an unstimulated well, largest in the monocytes,
is what a low basal secretion by monocytes would look like, and the same
processes that make a stimulated well's late responses may be running at a
low level in the unstimulated one. Whether that is so is for the models to
say; the Reference is supplied as its own condition and is fitted like the
others.

One consequence to be aware of: in monocytes the stimulated wells can end
**below** the Reference at 240 min (pSTAT3 −0.34 under IFN-α, −0.55 under
LPS). Either the stimulated monocytes did not rise as much as the resting ones,
or the cells remaining in the stimulated wells are a different subset from
those remaining in the Reference well (3–6 % of events against 10 %). A drift
term and the stimulus response may therefore not simply add in monocytes.

## Decisions of the study team that the modelling should take as given

Decided by the people who own the question. They concern the observation
model, the data and how the result is judged; **they do not prescribe the
model**, which is the next section's business.

**The observation model, the same in every model**

1. **Observable, and where it lives.** For each readout the modelled median
   count is count(r, t) = background(r) + pSTAT(r, t) + drift(r, t), with
   pSTAT in counts, and the observable is arcsinh(count / 5), the scale on
   which the data are given. **The count is part of the model, not of the
   observation layer**: the background and any drift quantity are model
   parameters, and the observable is only the arcsinh of that count,
   log(count/5 + sqrt(1 + count·count/25)), with no scaling factor or offset
   outside the arcsinh. A fraction of the arcsinh signal is not a fraction of
   phosphorylated molecules, and statements about normalised shapes refer to
   the modelled pSTAT, not to the arcsinh values.
2. **Background (the basal level).** background(r) is a constant, non-negative
   count per readout, inside the arcsinh (15 values). Together with a model's
   own basal phosphorylation it reproduces the 0-min level; where the two
   cannot be separated, that is reported as something the data cannot
   distinguish.
3. **Readout scale.** pSTAT is modelled in counts, with one readout scale per
   phospho-site, shared by all populations and all stimuli (one antibody, one
   tube, one run); there is no scale per population. Differences in peak
   height between populations are then differences in the amount of
   phosphorylated STAT.
4. **The noise model is the fixed `sigma` column.** No fitted σ.
5. **Monocyte rows at 120 and 240 min carry the widened σ** described above.
   They are kept, not dropped.

**Parameters and data**

6. **Every stimulus condition is fitted for all five populations, and no
   condition is held out.** The lymphocyte rows under the colony-stimulating
   factors and under LPS are in the fit: they are the observation the question
   is about. Every stimulus carries at least one parameter of its own, a
   receptor input strength, which a held-out condition could not constrain.
7. **The populations of a well are simulated together.** A condition is a
   stimulus; the fifteen readouts of that condition are read from one
   simulation in which all five populations are present. This is a statement
   about the experiment, not about the model: the cells were in one well, and
   a model that cannot let one population's product reach another cannot
   represent the observation above. How the populations are represented, what
   they share and what they do not is the model builder's decision, declared
   with the model (decision 10).
8. **Before time zero the cells rested, without stimulus and without whatever
   starts at plating.** Each condition is pre-equilibrated with its stimulus
   input, any drift quantity and any production of secreted factors set to
   zero, so that a model's resting state is computed from its own rates rather
   than assumed; at time zero the stimulus input switches on, and the drift
   and production terms start in every condition, the Reference included. The
   drift of the unstimulated wells is therefore the change since time zero,
   which is how the data define it.

**How the result is judged**

9. **Verdicts hold within the tested model family and these decisions.**
   "Required", "permitted" and "excluded" mean: among the models compared
   here, under these assumptions. "All tested models inadequate" is a valid
   result.
10. **Data fit first; identifiability from the Fisher information; profiles
    only at the end.** Data fit and information criteria decide between the
    models. Which parameters or parameter combinations the data do not
    determine is read from the Fisher information at each optimum; many
    parameters will not be identifiable, and that is to be reported, not
    repaired. Profile likelihoods are computed only for the final selected
    model.
11. **Biology.** Every species and reaction corresponds to a named entity or
    process, lumping is declared with what it lumps, and a secreted factor
    that a model needs but the experiment did not measure is declared for what
    it is: an unmeasured species whose identity the data can only constrain
    through its effects. The receptor and its JAKs are one active complex (the
    panel has no phospho-JAK readout). The observation quantities of decisions
    1–3 — the modelled counts, their background and any drift parameters and
    states — are not pathway entities: they are declared as observation
    quantities and are exempt from this rule. Where a literature source
    disagrees with these measurements, the measurements win and the
    disagreement is recorded.

## The question, and what we suggest testing

**The question.** What kind of communication between the cell populations in
a well do these data require, and what kind can they exclude? Specifically:
what reaches the T, B and NK cells under LPS and under the colony-stimulating
factors, when does it appear, which populations produce it, and is the same
communication already running at a low level in the unstimulated wells?

We do not know the answer. The candidate explanations below are what the
numbers above make us suspect. They are suggestions for what to test, not a
design to implement; the model builder decides what to build and the
comparison decides what the data support.

1. **A type I interferon secreted by monocytes**, acting on every population
   through the same receptor that the IFN-α wells stimulate directly, so its
   effect in each population is already calibrated by those wells. This would
   explain why the late LPS response of each population resembles that
   population's own IFN-α response.
2. **An IL-6-like factor secreted by monocytes**, acting on STAT3 above all.
   This would explain the late STAT3 in T cells under LPS and under the
   colony-stimulating factors, and the absence of late STAT1 in B and NK cells
   under the colony-stimulating factors.
3. **Interferon-γ from NK or T cells**, produced after signals from the
   monocytes, acting on STAT1. The NK cells' own numbers speak against this as
   the whole story: they show no STAT1 response to added IFN-γ within the
   window and a strong late STAT1 response under LPS.
4. **No secreted factor at all**: the late lymphocyte responses are direct,
   through receptors on the lymphocytes themselves, delayed by something in
   the cells. We consider this unlikely on the timing (nothing for an hour,
   then everything), but it is the null the others must beat.
5. **The same at a low level in the unstimulated wells.** If a secreted factor
   explains the stimulated wells' late responses, the unstimulated wells' slow
   rise in pSTAT3 and pSTAT5 may be the same factor at a basal production rate
   that starts at plating, rather than an unrelated drift.

These are not mutually exclusive: one, two or all of them may be needed, and a
combination of an interferon-like and an IL-6-like factor is our current best
guess for LPS. What we would like the comparison to establish, within the
tested family: which of these the data require, permit or exclude; when the
secreted factors appear and how long they last; whether their per-population
effects are the ones the direct wells predict; and which lymphocyte responses
remain unexplained. A model may of course propose a communication we have not
listed.

**What the data cannot decide by construction, as far as we can tell.** The
identity of a secreted factor is constrained only through its effects on the
STATs of five populations; two factors with the same STAT signature and the
same receptor distribution are one factor to these data. The absolute amount
of any factor is not measured, so only its timing and its relative effect
across populations are informative. The late monocyte rows are weak.

**What would settle it outside these data.** An IFNAR-blocking antibody in the
LPS well, an IL-6-receptor block, a monocyte-depleted culture, or a cytokine
measurement of the medium at 1, 2 and 4 h. None of these were done; a model
that names which of them would discriminate between its surviving candidates
has done its job.

## Where the literature bears on this note (knowledge module, 2026-09-29)

The knowledge module's dossier (`knowledge/`) carries what is known about this
system; the modelling agents receive it directly. Three points bear on
statements in this note and are recorded here, as decision 11 asks; where they
disagree with the measurements, the measurements win.

1. **The source study read the late responses as communication.** The authors
   reported that monocytes respond to LPS first and B, T and NK cells only at
   later time points, and attributed this to IL-6 or other monocyte-released
   factors (fact_22). The question here remains ours: that reading is among the
   candidate explanations above (1 and 2), not a result this analysis assumes.
2. **Published cytokine kinetics are slower than the onset seen here.** After
   LPS, bulk IL-6 and TNF protein peak at 4–6 h, and LPS-induced IFN-β takes
   hours to accumulate (fact_9, fact_10), while the lymphocyte responses in these
   wells begin between 60 and 120 min. The measurements win; the tension is
   reported, not resolved by assumption.
3. **The shared medium is treated as well mixed.** That a secreted factor
   reaches every population within minutes is an assumption of this note; one
   source argues that consumption by receptor-bearing cells can keep a factor
   local within a well (fact_19, graded none). The models keep the well-mixed
   assumption.
