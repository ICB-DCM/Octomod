# Mechanistic modelling before Octomod

A mechanistic model explains measurements with the processes that produce
them: species, the reactions between them, and their rates, written as
ordinary differential equations, $\dot{x} = f(x)$. Building one has usually
followed the same steps, carried out by hand by a modeller:

```{figure} figures/modelling_before.svg
:alt: Five steps in sequence (research question; literature and data; reduce to essentials; build the model; fit and gain insight) and a sixth, adjust if needed, that loops from the fit back to any earlier step.
:width: 100%

How mechanistic modelling has been done. Steps 2 to 6 are a loop: a model
that does not fit sends the modeller back to the data, the assumptions or the
model's form.
```

1. **Research question.** What should the model explain or predict?
2. **Literature and data.** What is already known about the system, and what
   can be measured?
3. **Reduce to essentials.** Keep only the parts and interactions the
   question needs.
4. **Build the model.** Choose the model's form: which reactions, with which
   rate laws. This is the step that needs the most modelling expertise.
5. **Fit and gain insight.** Estimate the parameters from the data, simulate,
   and interpret.
6. **Adjust if needed.** A mismatch between model and data sends the modeller
   back to any earlier step.

Every pass through the loop is a set of decisions — which mechanism to try
next, which data to trust, when a fit is good enough — and the reasons for
them are kept, if at all, in the modeller's notes rather than with the model.

## What Octomod changes

Octomod keeps these steps and the loop, and changes who does what:

| Step | In Octomod |
|---|---|
| 1 · Research question | The person states it; Octomod writes it down with them as the run's *intent*, and the run cannot start until they confirm it. |
| 2 · Literature and data | A knowledge module collects what is known about the system, with the source behind each claim, and grades how well each reaction is supported. |
| 3 · Reduce to essentials | The person sets how much support a reaction needs. By default reactions below it are flagged for review; in strict mode they stay out of the first model. |
| 4 · Build the model | AI agents draft the model and the alternative mechanisms worth testing; checks test every draft, and the person decides which mechanisms are tested. |
| 5 · Fit and gain insight | The engine fits every candidate, compares them, and tests them on data it held back. |
| 6 · Adjust if needed | When the models miss something, an agent proposes what the model space lacked; the person decides whether to spend another round on it. |

Every decision on this loop, whoever made it, is kept in one file with the
model: the run's *record*. To see the whole loop on real data, read
[a real run, start to finish](examples/ctd_blind/walkthrough.ipynb); to try it
on your own, [get started](getting-started.md).
