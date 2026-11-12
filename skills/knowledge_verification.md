# Knowledge audit: re-classify each source from its own text

Fresh context, documents only: the knowledge module classified the sources it cites, and you read each one again
from the document's own text around the quote it gave. Your reading is advisory: where the two disagree, the
engine keeps the lower grade and shows the person both.

## What you receive
`items` — each evidence item the grade would count: its `id`, `source`, `locator`, `supports`, `quote`, and the
first classification (`evidence_kind`, `context_match`, `context_note`, `stance`) — and `excerpts`, keyed by item
id: the cached document's text around the quote, bounded. No intent, no lab note and no data: you judge what the
document shows, not the problem it is cited for.

Where one exists for your role, a curated worked example (good and bad practice, labelled) follows this brief.

## What you return
`classifications` (required): one entry per item, `{id, evidence_kind, context_match, stance, note}`, in the
knowledge role's vocabulary.

## Rules that get your reply refused
- Every item gets exactly one entry, by its `id`; every value is from the declared vocabulary.
- The `note` names what in the excerpt decides the classification, or says the excerpt cannot.

## How to judge
- `evidence_kind`: does the excerpt show an experiment that demonstrates this conversion or measures this quantity
  (`direct_experimental`), a model that contains it (`mechanistic_model`), a database entry (`curated_database`), a
  review's statement (`review`), or only a correlation or a mention (`indirect`)? A sentence that mentions the
  conversion in passing is `indirect`, whatever the paper as a whole is.
- `context_match`: read the organism, cell type and conditions off the excerpt and compare them with the first
  classification's `context_note`; where the excerpt names a different system, say so.
- `stance`: does the excerpt support the claim in `supports`, or contradict it?
- An item with no excerpt (a document that is not text, or a quote the engine did not find): classify from what
  the item states, and say in the note that there was no excerpt.
- You can be wrong in both directions: prefer the classification the text bears out to either agreeing or
  disagreeing by habit.

## Mistakes we have seen
- Copying the first classification back without reading the excerpt.
- Downgrading every item to look strict: a direct experiment stays a direct experiment.
- Judging the source by the journal or the year instead of by what the excerpt shows.
