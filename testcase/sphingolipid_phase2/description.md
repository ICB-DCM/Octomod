# Sphingolipid metabolism: two-tracer pulse-chase, structural comparison (phase 2)

The user's own reaction network is supplied in `supplied/network.json`, translated
one to one from their SBML model. It is the **base model**. Phase 1 (run
`sphingo_phase1b`) fitted it as it stands. In phase 2 the user wants to test
specific changes to its structure, listed below, and find out which structure the
data support.

## The experiment

Neuroblastoma cells were labelled for 60 min with two alkyne-lipid tracers at once:
1 µM alkyne sphinganine and 50 µM alkyne palmitate, the palmitate additionally
carrying heavy 13C isotopes. The label was then removed and the chase followed at
0, 15, 30, 60, 120 and 180 min, with t = 0 the end of the pulse. There is one
experimental condition. Each time point is a separate sample.

## The measurements

LC-MS lipidomics with internal standards, giving absolute amounts in pmol per
sample for individual labelled lipid species. There are 3 biological replicates
(d1-d3), each measured as 3 technical replicates.

The table in `data/`:
- both tracers are summed per lipid class (one label);
- technical replicates are averaged within each biological replicate; the three
  biological replicates are separate rows (`replicate` d1-d3);
- each biological series is divided by its own total measured label at t = 0 (all
  lipid classes, both tracers). **The values are absolute fractions of the initial
  label, on the same scale as the model's amounts, so no scaling factor is needed
  between model and data.** The model's initial values in `network.json` are the
  t = 0 means on this scale;
- eleven pools are observed: free fatty acids (model species Pal), sphinganine
  (Sph), dihydroceramide, ceramide, sphingomyelin, hexosylceramide, PC, DG,
  cholesteryl ester, hexadecenal and hexadecanal. S1P and SA1P are not measured.
  No value is zero.

Measurement error: the user asks for an error that is estimated from the data and
proportional to the signal. In phase 1 a purely proportional error failed whenever
a predicted pool reached zero, so an additive plus proportional form is preferred.

The model species Pal stands for the whole labelled free-fatty-acid pool, not
palmitate alone, and Sph is sphinganine.

## What phase 1 found

The base model, fitted to this table:
- **Required:** a label influx into Pal and an outflux from DG; both intervals
  exclude zero.
- **Consistent with zero:** outflux from HexCer, CE and PC, the Pal sink, and
  SM → Cer. The data give only upper limits for these.
- **Pal + Ser → Sph** ran to near its upper bound (about 2e7), with only a lower limit.
- The fit is about 5.7 times worse than the spread between replicates. Much of that
  is a systematic offset between the biological replicates: d3 runs low in PC and
  high in SM and Pal at every time point. It is left in the data as variation.
- Sphingolipid label comes almost entirely from the sphinganine tracer. Palmitate
  label barely reaches ceramide within 3 h.

## The structural changes the user wants tested

These are the user's hypotheses, in their priority order. Each is a change to the
base model, to be tested against the base, not assumed.

1. **Sphinganine entry.** Is `Pal + Ser → Sph` needed, or is sphinganine purely the
   supplied tracer pool that is consumed downstream? Alternative: drop the
   reaction `Pal_to_Sph`.
2. **Hexadecenal route.** Literature on the S1P lyase pathway describes hexadecenal
   returning to palmitoyl-CoA through oxidation and CoA activation, not through
   reduction to hexadecanal. Alternative: replace `Hexdece_to_Hexdeca` with a
   direct `Hexdece → Pal`.
3. **Pruning the terms phase 1 found consistent with zero.** Alternative: remove
   `SM_to_Cer`, `HexCer_out`, `CE_out`, `PC_out` and `Pal_sink` together, as one
   change.

Deferred to a later round, not this one:
- whether the SA1P branch (`Sph_to_SA1P`, `SA1P_to_Hexdeca`) is needed;
- removing hexadecenal from the model entirely.

Nothing else about the network is to be changed. The base reactions, their mass-action
rate laws and the fixed initial values stay as supplied.
