# IFN-γ time course in GM-CSF-differentiated human macrophages (Xue et al. 2014, GEO GSE46903)

Lab note for the modelling team, written 2026-09-29 from the deposited data
and the paper's methods. The measurements are in `data/gmcsf_ifng_panel.csv`;
how that file was made from the raw deposit is `curation/make_panel.py` (the
raw files stay in `raw/`, outside what a run reads). GEO GSE47189 is the
study's SuperSeries; the arrays are its SubSeries GSE46903, and the raw file
`GSE47189_family.soft` holds both.

## Cells and stimulation (from the paper and its supplement)

- Human CD14+ monocytes, isolated with magnetic beads from buffy coats of
  healthy blood donors (University of Bonn).
- Differentiated into macrophages for 3 days (72 h) in RPMI1640 + 10 % FCS +
  PenStrep with GM-CSF (main text: "generated from monocytes by stimulation
  with GM-CSF or M-CSF for 72 hr"). The supplement's concentration line reads
  "500 IU/ml rhMCSF or 50 IU/ml MCSF" (sic), so the GM-CSF concentration is
  not certain from the text; the model does not use it.
- These baseline macrophages ("M0_GMCSF" in the sample titles) were then
  activated with IFN-γ at 200 IU/ml (Immunotools) and lysed after the stated
  time. Controls ("con") are baseline macrophages kept in culture without a
  stimulus and lysed at the matched time. The 0 h arrays are baseline
  macrophages lysed at the end of differentiation, before any stimulus.
- Whether IFN-γ remained in the culture for the whole interval (no wash-out)
  and whether the medium was changed at t = 0 are not stated in the paper.
  Working assumption (case owner, 2026-09-29): IFN-γ stays in the medium,
  a continuous stimulus from t = 0. Open to revision.

## What was measured

- Whole-genome expression on Illumina HumanHT-12 V3 BeadChips (GEO platform
  GPL6947), one array per sample, 12 arrays per chip; total RNA,
  biotin-labelled cRNA.
- Processing (supplement): Genome Studio, then Partek Genomics Suite: log2
  transform and quantile normalisation across all 384 arrays of the study.
  The supplement also says batch effects of separate array experiments were
  removed from the normalised log2 data; the GEO sample records describe the
  deposited VALUE only as "log2-transformed and normalized using quantile
  normalization with Partek Genomics Suite", so whether the deposited values
  include that batch step is not known.
- The paper computed an array background of 6.747 (log2 units) for the whole
  dataset and kept a gene only if its mean was above background in at least
  one condition.
- The four transcripts have exactly one probe each on this platform: IRF1
  ILMN_1708375, SOCS1 ILMN_1774733, CXCL9 ILMN_1745356, CXCL10 ILMN_1791759.
  The staged values are the deposited VALUE of those probes, copied verbatim.
- Each probe on each array also carries a detection p-value (the array's call
  whether the probe is above its negative-control beads). Over the 85
  eligible arrays IRF1 is detected (p ≤ 0.05) on every array; SOCS1 is not
  detected on 11 arrays, CXCL9 on 47, CXCL10 on 28, essentially all of them
  control arrays, where the values sit at 6.1–6.6 log2. A value there is the
  array's floor, not a measured abundance. The detection p-values are not in
  the staged file.

## The staged file

`data/gmcsf_ifng_panel.csv`, 81 rows, one array per row:

- `sample_id`: Sentrix barcode and section of the array. `array_chip`: the
  12-array chip it was on, a batch label; many donor series span chips.
- `donor`: the donor id as deposited. `BC85`, `BC85-1` and `BC85-2` are three
  distinct labels in the deposit and are kept distinct here.
- `stimulus`: `IFNg` or `control`. `time_h`: hours after stimulation (0.5 is
  the 30 min arrays).
- `IRF1_log2`, `SOCS1_log2`, `CXCL9_log2`, `CXCL10_log2`: log2
  quantile-normalised intensity. Already on the log scale; do not
  log-transform again. Arbitrary units, comparable across arrays after
  normalisation, not absolute concentrations.

Arrays per stimulus and time:

| time_h  | 0  | 0.5 | 1 | 2 | 4 | 6 | 12 | 24 | 48 | 72 |
|---------|----|-----|---|---|---|---|----|----|----|----|
| IFNg    | –  | 2   | 2 | 2 | 3 | 6 | 3  | 10 | –  | 7  |
| control | 27 | –   | – | – | – | 3 | 3  | 3  | 3  | 7  |

Who contributes what; the series are not balanced:

- Early series (0.5, 1, 2, 4, 6, 24 h IFN-γ plus an own 0 h control): donors
  BC964 and BC985. Donor BC974 contributes only 4, 6 and 24 h (see
  exclusions below).
- Mid series (6, 12, 24 h IFN-γ with time-matched controls at 6, 12, 24 and
  48 h): BC59, BC85-1, BC85-2. BC59 and BC85-2 also have 0 h controls; BC85-1
  has none of its own (two 0 h arrays are labelled plain `BC85`).
- 24 h only: BC69 and BC75, two IFN-γ arrays each at 24 h, no controls of
  their own.
- 72 h: BC11, BC13, BC52, BC58, BC76, BC78, BC9, each one IFN-γ array and one
  control array at 72 h.
- 0 h controls: 27 arrays from 24 donor labels; 20 of those donors appear
  nowhere else (they come from the wider study).

There is no error column: the donors are the replicates. Donor-to-donor
spread at 0 h is about 7.0–8.8 (IRF1), 6.3–7.8 (SOCS1), 6.1–6.6 (CXCL9) and
6.3–7.8 (CXCL10) log2.

## Arrays excluded, and one label conflict

85 arrays in the deposit satisfy the selection (platform GPL6947, initial
differentiation GM-CSF, activation stimulus IFNg or con). Four were excluded
because their values contradict their labels, all from donor BC974: its
"0 h control" (4958478044_J) has IRF1 10.0 and CXCL10 8.4, i.e. looks
stimulated; its "30 min" and "1 h" arrays look like 4 h or more of IFN-γ
(CXCL9 8.7 and 11.3, CXCL10 12.0 and 13.7); its "2 h" array looks
unstimulated (IRF1 6.8, CXCL10 6.4). BC974's 4, 6 and 24 h arrays agree with
the other donors at those times and are kept.

The two deposited files disagree about one pair of arrays on chip
4676163034: the SOFT family file labels section A "BC59 control 48 h" and
section F "TNF+PGE2+P3C 48 h, BC85-1"; the series matrix file swaps the two.
The staged file follows the series matrix (section F kept as the BC59 48 h
control; section A excluded). Section A has SOCS1 8.2 and IRF1 8.3, unlike
any other control array; section F (IRF1 7.4, SOCS1 6.9) looks like a
control.

## What the stimulated cells do

Medians of the arrays at each time under IFN-γ (log2), with the range in
brackets; the 0 h baseline is the 27 untreated arrays.

| time_h | n | IRF1 | SOCS1 | CXCL9 | CXCL10 |
|--------|---|------|-------|-------|--------|
| 0 (baseline) | 27 | 7.5 (7.0–8.8) | 6.7 (6.3–7.8) | 6.3 (6.1–6.6) | 6.5 (6.3–7.8) |
| 0.5 | 2 | 9.0 (8.9–9.2) | 6.7 (6.7–6.7) | 6.3 (6.2–6.3) | 6.9 (6.5–7.3) |
| 1 | 2 | 11.5 (11.4–11.5) | 7.7 (7.3–8.2) | 7.3 (7.1–7.5) | 10.8 (10.5–11.1) |
| 2 | 2 | 12.6 (12.4–12.7) | 8.2 (7.9–8.4) | 9.1 (8.6–9.7) | 13.5 (13.3–13.7) |
| 4 | 3 | 11.0 (10.4–12.0) | 9.4 (8.9–9.7) | 12.0 (11.2–12.8) | 14.1 (14.1–14.2) |
| 6 | 6 | 10.9 (10.7–11.2) | 9.5 (8.5–9.9) | 12.3 (10.3–12.8) | 14.0 (13.0–14.4) |
| 12 | 3 | 10.3 (9.6–11.1) | 9.9 (9.2–10.8) | 12.9 (12.0–12.9) | 14.3 (13.7–14.4) |
| 24 | 10 | 10.9 (9.7–11.9) | 8.3 (7.9–9.3) | 11.3 (10.7–12.4) | 13.3 (11.6–13.8) |
| 72 | 7 | 11.0 (10.3–11.5) | 7.4 (7.2–8.0) | 10.1 (8.9–10.6) | 11.9 (10.2–12.6) |

In words: IRF1 is up within 30 min, peaks by 2 h at about 5 log2 units above
baseline, and settles by 4 h to a plateau about 3.5 units above baseline that
holds to 72 h. SOCS1 rises more slowly, peaks at 6–12 h about 3 units above
baseline, and falls back most of the way by 72 h. CXCL9 and CXCL10 rise from
1 h, reach a plateau at 4–24 h (CXCL9 about 6 units, CXCL10 about 7.5 units
above baseline) and decline by 72 h, CXCL9 to about 4 units and CXCL10 to
about 5.5 units above baseline. The early arrays (0.5–4 h) are two donors,
BC964 and BC985 (three at 4 h), so the peak times rest on few arrays.

## What the untreated cells do

The time-matched controls are not flat. In the three mid-series donors CXCL10
rises in untreated cells at 6 h (8.9, 8.6 and 11.9 log2 against about 6.5 at
0 h) and 12 h (7.1, 7.0, 10.6) and is back near the floor by 24 h; SOCS1 is
at 7.2–7.3 at 6 h against 6.4–6.9 at 0 h; IRF1 moves within its 0 h donor
range. Donor BC85-2 shows the largest control excursion. The untreated 72 h
arrays sit at or near the 0 h levels, BC9 excepted (CXCL9 7.4, CXCL10 8.4).

## What the modellers asked for (the case owner's notes)

- An effective population-average transcription model: one effective
  regulatory activity downstream of IFN-γ (not a measured STAT1
  concentration) driving four transcripts, IRF1, SOCS1, CXCL9 and CXCL10;
  the stimulus an external input, not an estimated species; five states,
  optionally a sixth for an inhibitory feedback activity, for instance one
  produced from the SOCS1 transcript, with the measured SOCS1 mRNA kept
  distinct from any unmeasured protein activity.
- Per transcript: production = basal + activity-dependent, loss =
  first-order degradation; linear or simple saturating regulation, no freely
  estimated Hill exponents.
- Compare no feedback against one inhibitory feedback variable. Better curve
  fitting alone would not establish a SOCS mechanism.
- An explicit observation model on the log2 array scale; no second log
  transform, no per-time-point normalisation; intensities are not absolute
  concentrations.
- Kinetic parameters shared across donors; at most baseline or scaling
  differences between donors where the data support them; fit the individual
  arrays, not their averages.
- Use the pretreatment arrays to constrain the initial state; assume a basal
  steady state only if the controls allow it; a change in untreated
  expression must not be attributed to stimulation-induced feedback.
- Fix the scale of the unobserved activity; no redundant scaling parameters;
  constrain or drop its timescale if the data cannot resolve it; report
  profiles or intervals, not only best-fit curves.
- Out of scope: receptor binding, phosphorylation, nuclear transport,
  single-cell state switching, M1/M2 population counts, other stimuli or
  differentiation protocols, the ChIP-seq data, raw array reprocessing.
- No detection-threshold or censoring term in the noise model (case owner,
  2026-09-29); the detection p-values stay out of the staged file.
- The early arrays (0.5, 1, 2, 4 h) are in scope (case owner, 2026-09-29).

## What was not changed

Values are the deposited numbers. Nothing was rounded, re-normalised or
imputed. The raw deposit (`raw/GSE47189_family.soft`, 526 MB, and the two
series matrix files) is kept beside the case for audit and is not read by a
run.
