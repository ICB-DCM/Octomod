# Sphingolipid metabolism: two-tracer pulse-chase, supplied model

A complete PEtab problem is supplied: the user's model of sphingolipid metabolism
and a measurement table rebuilt from the raw lipidomics export. In this phase the
model is fitted as it stands. The aim is an honest account of what the data
determine, so that a later revision can be an informed one.

## The experiment

Neuroblastoma cells were labelled for 60 min with two alkyne-lipid tracers at once:
1 µM alkyne sphinganine and 50 µM alkyne palmitate, the palmitate additionally
carrying heavy 13C isotopes. The label was then removed and the chase followed
at 0, 15, 30, 60, 120 and 180 min, with t = 0 the end of the pulse. There is one
experimental condition. Each time point is a separate sample.

## The measurements

LC-MS lipidomics with internal standards, giving absolute amounts in pmol per
sample for individual labelled lipid species. Both tracers carry the alkyne tag;
species from the palmitate tracer additionally carry the 13C label, which makes the
two tracers distinguishable. There are 3 biological
replicates (d1-d3), each measured as 3 technical replicates (t1-t3).

The table fitted here:
- species are summed per lipid class, both tracers together;
- technical replicates are averaged within each biological replicate, and the three
  biological replicates are kept as separate data points;
- each biological series is divided by its own total measured label at t = 0 (all
  lipid classes, both tracers), so values are fractions of the initial label;
- eleven pools are observed: free fatty acids (model species Pal), sphinganine (Sph),
  dihydroceramide, ceramide, sphingomyelin, hexosylceramide, PC, DG, cholesteryl
  ester, hexadecenal and hexadecanal. S1P and SA1P are not measured;
- measurement error is taken as proportional to the signal, with one relative error
  per pool estimated from the data.

Note that the model species Pal stands for the whole labelled free-fatty-acid pool,
not palmitate alone, and Sph is sphinganine.

## What the data already show

Before any fitting:
- the sphingolipid pools carry almost only the sphinganine label, while PC, DG and
  cholesteryl ester carry almost only the palmitate label;
- total measured label falls by about a third over the chase and never rises;
- the biological replicates differ systematically: d1 is higher than d3 in nearly
  every pool, except sphinganine, where d3 retains the most. This is left in the
  data as variation, not corrected.

## What is wanted

Fit the supplied model. Report every estimated rate with an interval and say which
the data cannot pin down. Name any pool the model fits poorly. The constant influx
into Pal and the outflux terms are open questions for the user; report what the
fit says about them, without deciding them here.
