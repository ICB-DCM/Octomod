# Sensor–product module (bench note, 2026-09-08)

We have a small engineered two-part module in a cell-free extract and I want a
model of it that we can trust for dose extrapolation.

## What the parts are

There is a **sensor** protein that switches to an active form when we add the
small-molecule input, and switches back on its own. We read the active fraction
with a FRET sensor, so the number is a *fraction of total sensor* between 0 and
1, not a concentration — the total is fixed over the experiment and we
normalise it to 1.

The active sensor drives formation of a **product** we read by LC-MS in µM.
The product is also lost over the timecourse; we do not know by what route.

## The experiment

Three input doses in the same extract, `u = 0.5`, `2` and `8` (arbitrary units
of our stock — the same stock throughout, so only ratios are meaningful).
Sampled at 0, 5, 15, 30, 50, 80 and 120 minutes, two independent extract
preparations per dose. Both readouts on every sample.

Noise: the FRET read is good to about 0.03–0.04 in fraction units and the LC-MS
to about 0.1 µM, both from the replicate spread on our standards. Values at
t = 0 sometimes come out slightly negative; that is the additive noise around a
signal that is genuinely zero, and we have not clipped it.

## What I am unsure about, and would like the model to settle

1. **Does the product feed back on the sensor?** At the top dose the FRET
   trace does not look like a simple saturating rise to me — but I have been
   staring at it for a week and I no longer trust my eye. Nobody has shown
   feedback in this module and there is no structural reason to expect it.
2. **Is the sensor the only route to the product?** The input is a small
   molecule and I cannot rule out that it drives some product formation
   directly, without going through the sensor at all. If it does, it would be
   proportional to dose.
3. **Does product formation need one active sensor or two?** We assume one, but
   the sensor is known to dimerise in other contexts, and if the dimer is the
   active species then the rate would go with the square of the active
   fraction. I would expect that to show up as the product lagging the sensor
   more than it seems to.

## What is out of scope

No gene expression — this is cell-free. No growth, no dilution. No spatial
effects. Assume the sensor total and the extract composition are constant over
120 minutes.
