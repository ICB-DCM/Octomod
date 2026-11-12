# Sphingolipid metabolism in SH-SY5Y cells: two-tracer pulse-chase, revising a hand-built model

The user built a mechanistic model of sphingolipid metabolism by hand for these data (in
COPASI, exported as SBML). It is supplied as `supplied/network.json`, translated one to one
from that SBML, and it is the **base model**. The aim of this work is to improve on it. Some
reactions may be too detailed for these data, some included pools may not serve sphingolipid
metabolism itself, and some reactions may be missing. The goal is a biologically plausible
mechanistic model of sphingolipid metabolism that further research can build on.

## The experiment

- Human neuroblastoma SH-SY5Y cells, grown in DMEM/F12 with 10 % fetal calf serum and no
  antibiotics, in 12-well plates, at about 100 % confluence when labelled.
- Pulse: 60 min in medium containing two alkyne-lipid tracers together, **1 µM alkyne
  sphinganine** and **50 µM alkyne palmitate**. The palmitate additionally carries six 13C
  atoms, so the two tracers can be told apart.
- Chase: the pulse medium was removed, the cells washed once with unlabelled growth medium and
  kept in it. Samples were taken at 0, 15, 30, 60, 120 and 180 min, with t = 0 the end of the
  pulse. Each time point is a separate well.
- This is the **basal** (normal growth) condition only; there is one experimental condition.
- Replicates: 3 biological replicates (d1–d3, independent experiments) × 3 technical replicates.

## The measurements

- Lipids were extracted from the cells with methanol/chloroform. A mixture of internal
  standards (deuterated or odd-chain species for each lipid class, including alkyne-labelled
  standards) was added in the extraction mixture.
- The alkyne-labelled lipids were coupled to click-MS reporters, and samples were multiplexed
  and measured by direct-infusion MS/MS on a Thermo Q Exactive Plus. Species were identified
  with LipidXplorer.
- Values are absolute amounts in **pmol per sample**, from normalisation to the internal
  standards.
- **Which tracer a label came from** is read from the fragment detected:
  - the 13C6-alkyne fragment means 13C6-alkyne palmitate;
  - the non-isotope alkyne fragment means alkyne sphinganine.
  The label's position within a molecule (acyl chain or sphingoid backbone) is not resolved.
- **Double-labelled sphingolipids could not be quantified**, because there were no suitable
  internal standards. They are not in the data; their raw signals were very low compared with
  singly labelled species.

## The table fitted (`data/pulse_chase_fraction_of_initial_label.csv`)

Built from the raw export `supplied/data_all.csv`; every step is documented in
`curation/DATA_PROCESSING.md`.
- Both tracers are summed per lipid class, as **one label**. Single- and double-labelled
  species are counted together.
- Technical replicates are combined by their **median**. The three biological replicates are
  separate rows (`replicate` d1–d3).
- Each biological series is divided by its own total measured label at t = 0, summed over all
  measured classes. **The values are fractions of the initial label, on the same scale as the
  model's amounts, so no scaling factor is needed between model and data.** The initial values
  in `network.json` are the t = 0 means on this scale.
- Eleven pools are fitted:
  - free fatty acids (model species `Pal`; this is the whole labelled FFA pool, all chain
    lengths, not palmitate alone);
  - sphinganine (`Sph`), dihydroceramide, ceramide, sphingomyelin, hexosylceramide;
  - hexadecenal and hexadecanal;
  - PC, DG and cholesteryl ester.
  No fitted value is zero. S1P, SA1P and serine are not measured.
- **Measured but deliberately left out**: TG, PA, PE, PI and MG. The user built the model
  around the sphingolipid pathway, plus the three labelled classes outside it that were most
  abundant at t = 0 (PC, DG, CE). These five classes do count in the t = 0 total used for
  normalisation.
- No value was edited or excluded.

## Measurement error

The user asks for an error model that is **additive plus proportional** to the signal, with
both parts estimated from the data, per observable. The spread between the three technical
replicates was used only to form the median, not as a fixed error.

## What the raw data show, before any fitting

- The two labels barely mix:
  - sphinganine, dihydroceramide, ceramide, sphingomyelin and hexosylceramide carry almost only
    the sphinganine label; **sphinganine carries no palmitate label at all**;
  - PC, DG and CE carry almost only the palmitate label;
  - the FFA pool carries both.
- **Sphingolipid pools:**
  - sphinganine falls about eightfold over the chase, most steeply in the first 15 min;
  - dihydroceramide falls about sixfold;
  - ceramide stays near its t = 0 level for about 15 min, then falls about sevenfold;
  - sphingomyelin and hexosylceramide rise throughout, about threefold to fourfold.
- **FFA and glycerolipid pools:**
  - FFA label falls about threefold within the first 15 min and changes little after that;
  - DG falls about twelvefold;
  - PC stays roughly constant;
  - CE rises about twofold.
- Total measured label falls by about a quarter to a third over 180 min and never rises.
- **Biological replicates differ systematically**, beyond what dividing by the t = 0 total
  removes. d3 took up less label in total but holds a larger share of it in sphinganine and a
  smaller share in PC. This is left in the data as variation.
- Sphinganine is the noisiest pool between technical replicates (one technical replicate of d3
  at 60 min is four to five times its two neighbours; the median is used).

## Caveats on particular pools

- **Hexadecenal and hexadecanal** are low-abundance species, and most of their measured label
  is palmitate-derived. As sphingoid-base degradation starts from the sphinganine backbone,
  the user considers palmitate-derived label in these aldehydes **not explained by the
  canonical degradation pathway**. It may come from other routes or from misassignment of
  these low-abundance species. They are kept in the data, with this doubt.
- Sphinganine's steep early fall may partly reflect effects right after the pulse (high initial
  tracer abundance, dilution) that a mass-action model represents poorly.

## The round-1 model and the structure to test

The user's hand-built model (their SBML, 14 species and 21 irreversible mass-action reactions)
was restructured by the user on 2026-09-29, after a literature survey, into a round-1 model and
a set of hypotheses. `supplied/network.json` holds both: `species` and `interactions` are the
round-1 model, `hypotheses` the alternatives, with the extra reactions and species they use in
`hypothesis_reactions` and `hypothesis_species`. Each reaction's `note` gives the user's reason
for it and its status.

**Round-1 model, core reactions (7):** N-acylation of sphinganine with the FFA pool to
dihydroceramide (Sph + Pal -> DhCer); desaturation to ceramide; ceramide to SM and back
(sphingomyelinase); ceramide to HexCer; ceramide degradation to S1P (ceramidase and sphingosine
kinase collapsed; sphingosine not measured); loss of FFA label (Pal ->), core because fatty
acids have other functions than sphingolipid metabolism.

**Round-1 model, provisional reactions (9):** FFA into CE, DG and PC; outflux from HexCer, CE,
DG and PC; a constant influx of label into the FFA pool; a constant import of sphinganine
(-> Sph). They are fitted from round 1. Whether each is needed is a question the user wants
asked from the first expansion on, not in round 1.

**Placeholders:** hexadecenal and hexadecanal are measured and in the model, but no reaction
reaches them until an aldehyde hypothesis adds one; until then they are predicted flat.
Serine and SA1P are not in the round-1 model; they enter only with the hypotheses that use
them.

**Hypotheses to test in round 1, one at a time on the round-1 model:**
- **H1** ceramide degradation releases the fatty acid: Cer -> S1P + Pal instead of Cer -> S1P.
- **H2a / H2b** (competing): S1P -> hexadecenal, then either hexadecenal -> hexadecanal -> FFA
  (the user's original route) or hexadecenal -> FFA directly (the route in the literature).
- **H3a / H3b** (competing): sphinganine -> SA1P -> hexadecanal -> FFA, or the same with SA1P
  collapsed away (Sph -> hexadecanal -> FFA).
- **H5 / H5'** (competing with the import): de novo synthesis Pal + Ser -> Sph beside the
  sphinganine import (both), or instead of it (synthesis only).
Wherever a route reaches hexadecanal, hexadecanal -> FFA comes with it.

**Declared, not tested in round 1:** removing each of the nine provisional reactions (this
includes "neither import nor synthesis"). The user will test these from the first expansion
on.

Left to the expansion step, not named by the user: other reactions from the literature, if
the remaining misfit points to them.

Simplifications the user made on purpose:
- one compartment;
- one merged label;
- several enzymatic steps collapsed into one reaction where the note says so;
- sinks standing for material that leaves to, or comes from, processes outside the defined
  system.

The parameter bounds (1e-12 to 1e8) are the user's own, not measured values, kept for the
first run by the user's decision. Six HexCer species occur twice in the lipidomics export
(pairs about 1.008 Da apart, possibly the +1 isotope peak of the first); both rows of each pair
are kept and summed into the HexCer pool for the first run, also by the user's decision.

## What is wanted

- Translate the round-1 model faithfully, and declare each hypothesis above, and each
  declared-not-tested removal, as a structural alternative on it, as written in
  `supplied/network.json`.
- The result is reported **per hypothesis first**: whether the data support it, discard it or
  cannot decide it, and for each competing group which alternative the data prefer. A single
  final model is reported only after that.
- Where the data cannot tell two alternatives apart, the model reported as final uses the
  alternative with better literature support, and says that this choice was made on
  literature, not on the data.
- Where several reaction steps from the literature are collapsed into one reaction for the
  sake of identifiability, say so explicitly.
- Removing a measured pool entirely is decided by the user between runs, not inside this one.
