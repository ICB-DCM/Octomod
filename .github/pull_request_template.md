<!-- A PR missing one of the first five will be sent back.

     CI (.github/workflows/pr.yml) runs the style gates and the whole battery,
     group by group, on every push here, so this template no longer asks you to
     tick those off by hand — read the checks instead. What it still asks for
     is what CI cannot produce: the reasoning. -->

## Why
<!-- The problem, the evidence it exists, the alternative you rejected.
     Cite a run id / artifact path if a live run motivated this. -->

## What a run does differently
<!-- Not what the code does — what a RUN now does. "Nothing observable" is a
     legitimate answer; say it explicitly so the reviewer knows where to look. -->

## Where that is visible in the tests
<!-- Suite and assertion, by name. "The battery is green" is not an answer, and
     it is less of one now that CI turns it green without you: green before and
     after means the change is untested. -->
- suite:
- assertion:

## New testcase, if one was needed
<!-- Path under testcase/, and THE SPECIFIC RESULT YOU EXPECT: the numbers, the
     gate that should fire, the candidate that should win. The reviewer should be
     able to read your expected outcome before reading your code.
     Write "not needed — covered by <case>" if so. -->

## Reporting
<!-- A gate with no line in the report is a bug.
     Which surface did you touch? Paste the rendered line or panel.
     No suite can check this one, which is why it is still asked by hand. -->

## Checks
<!-- CI already runs `black --check`, `ruff check` and every suite of the
     battery on every push to this PR, including the guards you used to promise
     here: `speckeys` (README counts vs the registry),
     `tcleak` and `noleak` (benchmark truth leaking into templates), and the
     scientific suites — parameter recovery, held-out rejection, the model-space
     search. Read the result rather than re-asserting it. The one below is what
     CI cannot settle. -->
- [ ] I did not read `testcase/*/truth/` while developing this — or I said so
      above. <!-- No suite can know this; `tcleak` only catches truth reaching a
      template, not a person reading it. -->
