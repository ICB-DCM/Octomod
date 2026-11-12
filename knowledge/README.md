# Knowledge packs

A pack is modelling advice that the engine puts, as text, into the prompts of
some agents. It is written as pitfalls: a failure an experienced modeller
avoids, why it matters, and what an agent should do about it. A problem uses
the packs its intent names under `domain_packs`; a name that matches no pack is
refused when the intent is checked.

The pitfalls were drafted with an LLM and have not been reviewed entry by entry
by a domain expert. They are advice to the agents, not evidence. The graded
evidence of a run comes from the knowledge module (M0,
`octomod/workflow_modules/knowledge/`), which is separate from these packs.

| pack | layer | what it covers | written for (`applies_to`) |
|---|---|---|---|
| `general-dynamics` | general | bounds and scaling, timescales and the data window, conservation, identifiability; also standard reaction forms (`templates.md`) | `construction`, `observation`, `interpretation`, `revision_proposal` |
| `measurement-tech` | measurement | immunoblot densitometry, plate-reader and fluorescence intensities, digitised figure data, replicates and error bars | `data_extraction`, `observation`, `assembly_verification` |
| `signalling-phospho` | domain | phosphorylation signalling over minutes to hours: conserved pools, basal phosphatase activity, timescale separation, dose through receptor occupancy, antibody specificity | `construction`, `observation`, `condition`, `interpretation`, `revision_proposal` |

`applies_to` records which agents a pack was written for; the engine does not
read it. Every pack the intent names goes to the agents whose context includes
`domain_packs` in [`docs/ROUTING.md`](../docs/ROUTING.md): `construction`,
`expansion`, `observation`, `assembly_verification` and `revision`.

```
knowledge/packs/<pack>/
  pack.yaml      # id, version, layer, scope, applies_to, curation status, provenance
  pitfalls.md    # the entries: Pitfall, Why it matters, How to apply
  templates.md   # optional: standard reaction forms
```

The engine joins `pitfalls.md` and `templates.md` (and `examples.md`, if a pack
has one) and passes the text on unchanged; it never interprets a pack. Of
`pack.yaml` it checks only that the file exists. Each agent's prompt, with the
pack text in it, is kept in the run record.
