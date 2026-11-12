# Octomod

Octomod builds mechanistic models from data with the help of AI agents, inside
a deterministic, gated engine: agents draft the model, the reading of the data,
the observation model and the interpretation; checks test every draft; and a
person decides at every step that costs compute or makes a scientific claim.
Everything a run did is kept in one file, its *record*.

::::{grid} 1 1 2 2
:gutter: 3

:::{grid-item-card} Mechanistic modelling before Octomod
:link: background
:link-type: doc

The steps a modeller has taken by hand, and what Octomod changes about each.
:::

:::{grid-item-card} Getting started
:link: getting-started
:link-type: doc

Install Octomod, and stage your own problem: your data, your question, and
the decisions that are yours.
:::
::::

The best way to see what that means is one real run, start to finish:

::::{grid} 1
:::{grid-item-card} A real run: P-TEFb and the RNA polymerase II CTD
:link: examples/ctd_blind/walkthrough
:link-type: doc

A biochemist's question about how a kinase modifies an 8-repeat substrate,
answered from 36 mass-spectrometry numbers in two rounds of candidate models:
every prompt, check, decision and model, the stop and restart on the way, and
the answer — including what the data cannot decide.
:::
::::

```{toctree}
:hidden:

background
getting-started
```

```{toctree}
:caption: Example · the CTD run
:maxdepth: 1
:hidden:

examples/ctd_blind/walkthrough
examples/ctd_blind/explore_record
examples/ctd_blind/prompts/index
```
