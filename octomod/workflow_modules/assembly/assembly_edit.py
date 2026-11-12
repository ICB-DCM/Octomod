"""Assembly edits: the observation layer as a patchable artifact.

The one executor for assembly edits: the revision loop (`apply_move`) and the
model-space observation axes (`on_assembly_patch`) both go through `apply_patch`.
A patch is `{"<kind>": {...args}}`, one kind per patch; an observable or a
condition is named by id or by data label, which `resolve_refs` turns into ids.

Kinds (the agent contract and skills/observation.md name the same list):
  change_observable_formula {observable, new_formula}
  change_noise_model        {observable, new_distribution?, new_formula?, new_per?}
                            new_formula: "sigma_x" or "sigma_x * <expr>" (proportional)
                            new_per: observable | condition (what a sigma is per)
  add_offset / remove_scaling {observable}
  change_scaling            {observable | observable_ids, per,
                             shared_across_observables?, pin_first_to_one?}
                            per: observable | timepoint | condition
  change_condition {condition, overrides}  hypothesis class only: adds or
                            removes an override key; changing an existing value
                            or the pre-equilibration declaration is refused
  split_parameter           {parameter_id, by}      one copy per value of condition
                            attribute `by`, in every condition (resolve_split)
  change_transformation     {observable, new}       declared, refused until
                            criterion comparability exists
"""

from __future__ import annotations

import copy
import re

from octomod.workflow_modules.estimation.problem import FITTABLE_NOISE_DISTRIBUTIONS

# Formula-symbol extraction lives here only; `gates/petab_gates.py` imports `symbols`.
TOKEN = re.compile(r"[A-Za-z_]\w*")
# The words a patch may use without declaring them: math vocabulary, not symbols.
MATH_WORDS: frozenset[str]
PLACEHOLDER = re.compile(r"^(noise|observable)Parameter\d+_\w+$")
_MATH_WORDS = {
    "exp",
    "log",
    # the natural log, as sympy, PEtab and libSBML spell it
    "ln",
    "log10",
    "log2",
    "sqrt",
    "abs",
    "min",
    "max",
    "pow",
    "pi",
    "time",
    "t",
    "inf",
    "nan",
}
MATH_WORDS = frozenset(_MATH_WORDS)

# Functions AMICI's PEtab/SBML import accepts in an observable or noise formula.
# Antimony, roadrunner and petab also accept `log2`/`log10`, which AMICI's import
# does not; petab.v1.math.sympify_petab rewrites them into log(x)/log(b).
AMICI_FUNCTIONS = frozenset(
    {"exp", "log", "sqrt", "abs", "min", "max", "pow", "piecewise", "sin", "cos", "tan"}
)
_FUNC_CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
_REWRITE_FUNCS = ("log2", "log10")
# renamed textually, so the rest of the formula stays byte-identical
_RENAME_FUNCS = {"ln": "log"}


def unsupported_functions(formula: str) -> list[str]:
    """Sorted names of the functions called in `formula` that AMICI cannot compile."""
    return sorted(
        {
            f
            for f in _FUNC_CALL.findall(str(formula))
            if f.lower() not in AMICI_FUNCTIONS
        }
    )


def amici_safe_formula(formula: str) -> str:
    """AMICI-compilable spelling: `ln` -> `log`, `log2`/`log10` rewritten by petab.

    Any other formula is returned byte-identical. Raises ValueError naming a
    function AMICI does not know.
    """
    text = str(formula)
    for old, new in _RENAME_FUNCS.items():
        text = re.sub(rf"\b{old}(\s*\()", rf"{new}\1", text)
    if any(re.search(rf"\b{f}\s*\(", text) for f in _REWRITE_FUNCS):
        from petab.v1.math import sympify_petab

        text = str(sympify_petab(text))
    bad = unsupported_functions(text)
    if bad:
        raise ValueError(
            f"formula calls {bad}, which AMICI cannot compile "
            f"(allowed: {sorted(AMICI_FUNCTIONS)}): {formula!r}"
        )
    return text


KINDS: dict[str, list[str]] = {
    "change_observable_formula": ["new_formula"],
    "change_transformation": ["new"],
    "change_noise_model": [],
    "add_offset": [],
    "remove_scaling": [],
    "change_scaling": ["per"],
    "change_condition": ["overrides"],
    "split_parameter": ["parameter_id", "by"],
}
OBSERVABLE_KINDS = {
    "change_observable_formula",
    "change_transformation",
    "change_noise_model",
    "add_offset",
    "remove_scaling",
    "change_scaling",
}
# Owned by the estimation path: a distribution the assembly accepts must be one
# the optimiser can evaluate.
DISTRIBUTIONS = FITTABLE_NOISE_DISTRIBUTIONS
# What a sigma is indexed by: `condition` gives one sigma set per condition, for a
# spread that differs between arms of the design.
NOISE_PER = ("observable", "condition")
# What a scale factor is indexed by: one per observable, per distinct measurement
# time (a per-injection mass-spec gain) or per condition (separate gels, plates,
# days). The contract, the skill, the renderer and the drift test read this tuple.
SCALING_PER = ("observable", "timepoint", "condition")
# The optional scaling-block fields, named once for the drift test.
SCALING_FIELDS = ("per", "shared_across_observables", "pin_first_to_one")


def symbols(formula: str) -> set[str]:
    return {
        tok
        for tok in TOKEN.findall(str(formula))
        if tok not in _MATH_WORDS and not PLACEHOLDER.match(tok)
    }


def patch_kind(patch: dict) -> tuple[str, dict]:
    """(kind, args) for a well-formed patch; ValueError otherwise."""
    if not isinstance(patch, dict) or len(patch) != 1:
        raise ValueError(
            "an assembly patch is a dict with exactly one kind as key; kinds: "
            f"{sorted(KINDS)}"
        )
    kind, args = next(iter(patch.items()))
    if kind not in KINDS:
        raise ValueError(
            f"unknown assembly patch kind {kind!r}; known: {sorted(KINDS)}"
        )
    if not isinstance(args, dict):
        raise ValueError(f"{kind}: arguments must be a dict")
    return kind, args


def describe(patch: dict) -> str:
    try:
        kind, args = patch_kind(patch)
    except ValueError as e:
        return f"(malformed patch: {e})"
    if kind == "split_parameter":
        n = len(set((args.get("copies_by_condition") or {}).values()))
        return (
            f"split_parameter({args.get('parameter_id')} by {args.get('by')}"
            + (f", {n} copies" if n else ", unresolved")
            + ")"
        )
    target = (
        args.get("observable_id")
        or args.get("observable_label")
        or args.get("condition_id")
        or args.get("condition_label")
        or (",".join(map(str, args.get("observable_ids") or [])) or None)
        or "?"
    )
    extra = {
        k: v
        for k, v in args.items()
        if k
        not in (
            "observable_id",
            "observable_label",
            "observable_ids",
            "condition_id",
            "condition_label",
        )
    }
    return f"{kind}({target}" + (f", {extra}" if extra else "") + ")"


def patch_targets(patch: dict) -> list[str]:
    """What a patch targets, for `validate_axes`'s one-axis-per-target rule.

    The observables of an observable kind (the whole `observable_ids` list for a
    group `change_scaling`), else the condition, or `parameter:<id>` for a split.
    """
    kind, args = patch_kind(patch)
    if kind == "split_parameter":
        # a parameter, not an observable or a condition: two splits of one
        # parameter clash, a split never clashes with a readout's axis
        return [f"parameter:{args.get('parameter_id')}"]
    if kind not in OBSERVABLE_KINDS:
        return [str(args.get("condition_id") or args.get("condition_label") or "?")]
    if args.get("observable_ids"):
        return [str(x) for x in args["observable_ids"]]
    return [str(args.get("observable_id") or args.get("observable_label") or "?")]


def validate_patch(
    patch: dict,
    *,
    model_entities: set[str],
    parameter_ids: set[str],
    adds: set[str] | None = None,
    assembly: dict | None = None,
) -> list[str]:
    """The problems with a patch, checked before any compile (empty = fine).

    With `assembly`, the observable/condition references and the condition
    hypothesis-class rule are checked too; without it (a construction-declared
    axis) they are deferred to assembly time.
    """
    try:
        kind, args = patch_kind(patch)
    except ValueError as e:
        return [str(e)]
    problems = []
    for req in KINDS[kind]:
        if req not in args:
            problems.append(f"{kind}: missing argument {req!r}")
    if kind in OBSERVABLE_KINDS and not (
        args.get("observable_id")
        or args.get("observable_label")
        or (kind == "change_scaling" and args.get("observable_ids"))
    ):
        problems.append(
            f"{kind}: needs observable_id or observable_label"
            + (
                " (or observable_ids for a shared group)"
                if kind == "change_scaling"
                else ""
            )
        )
    if kind == "change_condition" and not (
        args.get("condition_id") or args.get("condition_label")
    ):
        problems.append(f"{kind}: needs condition_id or condition_label")
    if problems:
        return problems

    if kind == "change_transformation":
        # comparing likelihoods across transformations without the
        # change-of-variables correction would let the search "discover" that
        # log-transforming improves AIC: refused until that correction exists
        return [
            f"{kind}: a transformation axis needs a criterion that compares "
            f"fits on different residual scales, which the engine does not "
            f"have — refused, not silently compared"
        ]

    known = set(model_entities) | set(parameter_ids) | set(adds or ())
    if kind == "change_observable_formula":
        unresolved = symbols(args["new_formula"]) - known
        if unresolved:
            problems.append(
                f"{kind}: new_formula uses unknown symbol(s) " f"{sorted(unresolved)}"
            )
    if kind == "change_noise_model":
        if not any(k in args for k in ("new_distribution", "new_formula", "new_per")):
            problems.append(
                f"{kind}: needs new_distribution, new_formula and/or new_per"
            )
        if "new_distribution" in args and args["new_distribution"] not in DISTRIBUTIONS:
            problems.append(f"{kind}: new_distribution must be one of {DISTRIBUTIONS}")
        if "new_per" in args and args["new_per"] not in NOISE_PER:
            problems.append(f"{kind}: new_per must be one of {NOISE_PER}")
        if "new_formula" in args:
            syms = symbols(args["new_formula"])
            sigma_like = {s for s in syms if s.startswith("sigma")}
            current_sigma = set()
            if assembly is not None:
                oid = _resolve_observable(args, assembly, strict=False)
                for n in assembly.get("noise", []):
                    if n.get("observable_id") == oid:
                        current_sigma |= symbols(str(n.get("formula", "")))
            unresolved = syms - known - sigma_like - current_sigma
            if unresolved:
                problems.append(
                    f"{kind}: new_formula uses unknown symbol(s) "
                    f"{sorted(unresolved)} (allowed: model entities, "
                    f"declared parameters, a sigma_* parameter)"
                )
            if len(sigma_like | current_sigma) > 1 and len(sigma_like) > 1:
                problems.append(
                    f"{kind}: new_formula names more than one sigma "
                    f"parameter {sorted(sigma_like)}"
                )
    if kind == "change_scaling":
        per = str(args.get("per"))
        if per not in SCALING_PER:
            problems.append(f"{kind}: per must be one of {SCALING_PER}, not {per!r}")
        shared = args.get("shared_across_observables", False)
        if shared not in (False, None) and not (
            isinstance(shared, str) and shared.strip()
        ):
            problems.append(
                f"{kind}: shared_across_observables is false or a GROUP NAME "
                f"(one parameter set shared by every observable in the group)"
            )
        if args.get("observable_ids") is not None and not (
            isinstance(args["observable_ids"], list) and args["observable_ids"]
        ):
            problems.append(f"{kind}: observable_ids must be a non-empty list")
        if args.get("pin_first_to_one") and per == "observable":
            problems.append(
                f"{kind}: pin_first_to_one only means something with "
                f"per=timepoint or per=condition — there is no 'first' factor "
                f"to pin when there is one factor"
            )
    if kind == "change_condition":
        ov = args.get("overrides")
        if not isinstance(ov, dict) or not ov:
            problems.append(f"{kind}: overrides must be a non-empty dict")
        else:
            bad = [k for k in ov if k not in model_entities]
            if bad:
                problems.append(
                    f"{kind}: override key(s) {bad} are not model "
                    f"parameters or species"
                )
            # A parameter-id value is the condition's own copy of a parameter and
            # must be declared (adds_parameters) so its row says whether it is
            # estimated; an undeclared copy of a fixed parameter would be a no-op.
            known_ids = (
                set(parameter_ids)
                | set(adds or ())
                | {
                    str(x)
                    for c in (assembly or {}).get("conditions", [])
                    for x in (c.get("overrides") or {}).values()
                    if isinstance(x, str)
                }
            )
            for k, v in ov.items():
                if v is None:
                    continue
                try:
                    val = override_value(v)
                except ValueError as e:
                    problems.append(f"{kind}: {e}")
                    continue
                if isinstance(val, str) and val not in known_ids:
                    problems.append(
                        f"{kind}: override {k!r} -> {val!r} names a parameter "
                        f"nobody declares — declare it in adds_parameters with "
                        f"its bounds and estimate flag (an undeclared copy "
                        f"would inherit {k!r}'s)"
                    )
    if kind == "split_parameter":
        pid = str(args.get("parameter_id"))
        copies = args.get("copies_by_condition") or {}
        if pid not in set(parameter_ids):
            problems.append(f"{kind}: {pid!r} is not a parameter of the model")
        if not copies:
            problems.append(
                f"{kind}: unresolved — the engine resolves a split against the "
                f"data's conditions (resolve_split) before it is validated; it "
                f"is proposed at the expansion gate, where both exist"
            )
        else:
            undeclared = sorted(
                {c for c in copies.values() if c not in set(adds or ())}
            )
            if undeclared:
                problems.append(
                    f"{kind}: copies {undeclared[:4]} are not declared in adds_parameters"
                )
            clash = sorted({c for c in copies.values() if c in set(model_entities)})
            if clash:
                problems.append(
                    f"{kind}: copies {clash[:4]} collide with model entities"
                )
            if assembly is not None:
                ids = {c["condition_id"] for c in assembly.get("conditions", [])}
                uncovered = sorted(ids - set(copies))
                if uncovered:
                    # an estimated parameter split in some conditions only would
                    # leave the rest reading its nominal
                    problems.append(
                        f"{kind}: conditions {uncovered[:4]} have no copy of {pid!r} "
                        f"— a split covers every condition"
                    )
                enc = [
                    c["condition_id"]
                    for c in assembly.get("conditions", [])
                    if pid in (c.get("overrides") or {})
                ]
                if enc:
                    problems.append(
                        f"{kind}: {pid!r} is already set per condition in {enc[:4]} — "
                        f"a measured factor or an existing split is not split again"
                    )
        return problems
    if assembly is not None and not problems:
        try:
            resolve_refs(patch, assembly)
        except ValueError as e:
            problems.append(str(e))
        if kind == "change_condition" and not problems:
            problems += _condition_class_problems(args, assembly)
    return problems


def condition_attributes(
    assembly: dict, key_by_label: dict[str, str]
) -> dict[str, dict]:
    """{condition_id: {attribute: value}} from the data's condition keys.

    `key_by_label` maps a data label to its condition key ('col=val|col=val', from
    `data.condition_key`); display labels are never parsed.
    """
    out: dict[str, dict] = {}
    for c in assembly.get("conditions", []):
        key = key_by_label.get(str(c.get("maps_to_label")))
        if key is None:
            continue
        out[c["condition_id"]] = dict(
            part.split("=", 1) for part in str(key).split("|") if "=" in part
        )
    return out


def _id_safe(value) -> str:
    """A value as the tail of an id (`k_cat1_` + `0`, `kdeph_` + `Tcell_CD4`):
    word characters only; a leading digit is fine after the underscore."""
    return re.sub(r"\W+", "_", str(value)).strip("_") or "v"


def resolve_split(
    args: dict,
    assembly: dict,
    condition_values: dict[str, dict],
    base_parameters: list[dict],
    trained_ids: set[str] | None = None,
) -> tuple[dict | None, list[str]]:
    """Resolve `split_parameter {parameter_id, by}` against the data's conditions.

    One copy of the parameter per value of the condition attribute `by`, in every
    condition, each row copied from the base parameter's. Every condition gets a
    copy because an estimated parameter overridden in only some would read its
    nominal in the rest; the axis adds (values - 1) estimated parameters net.
    Returns ({on_assembly_patch, adds_parameters}, []) or (None, problems).
    """
    kind = "split_parameter"
    pid = str(args.get("parameter_id") or "")
    by = str(args.get("by") or "")
    rows = {str(p.get("id")): p for p in base_parameters or []}
    if pid not in rows:
        return None, [f"{kind}: {pid!r} is not a parameter of the base model"]
    if not rows[pid].get("estimate", True):
        return None, [
            f"{kind}: {pid!r} is fixed — there is nothing to estimate per {by}"
        ]
    conds = [c["condition_id"] for c in assembly.get("conditions", [])]
    enc = [
        c["condition_id"]
        for c in assembly.get("conditions", [])
        if pid in (c.get("overrides") or {})
    ]
    if enc:
        return None, [
            f"{kind}: {pid!r} is already set per condition in {enc[:4]} — a measured "
            f"factor or an existing split is not split again"
        ]
    attrs = sorted({k for v in condition_values.values() for k in v})
    missing = [c for c in conds if by not in (condition_values.get(c) or {})]
    if missing:
        return None, [
            f"{kind}: condition(s) {missing[:4]} carry no {by!r} in the data's "
            f"condition key (attributes: {attrs})"
        ]
    value_of = {c: str(condition_values[c][by]) for c in conds}
    values = sorted(set(value_of.values()))
    if len(values) < 2:
        return None, [
            f"{kind}: every condition has {by}={values[0] if values else '?'} — nothing to split"
        ]
    if trained_ids is not None:
        seen = {value_of[c] for c in conds if c in trained_ids}
        orphan = [v for v in values if v not in seen]
        if orphan:
            return None, [
                f"{kind}: {by} value(s) {orphan} appear only in held-out conditions — "
                f"their copies of {pid!r} could not be estimated from training data"
            ]
    copy_of = {v: f"{pid}_{_id_safe(v)}" for v in values}
    if len(set(copy_of.values())) < len(values):
        return None, [
            f"{kind}: the {by} values {values} do not give distinct parameter ids"
        ]
    taken = sorted({c for c in copy_of.values() if c in rows})
    if taken:
        return None, [
            f"{kind}: copy ids {taken[:4]} are already parameters of the base model"
        ]
    template = {
        k: v
        for k, v in rows[pid].items()
        if k not in ("id", "neutral_value", "layer", "denotes", "source")
    }
    adds = [
        {
            **template,
            "id": copy_of[v],
            "denotes": f"{pid} for {by}={v} — one copy per {by} (split_parameter)",
            "source": f"copy of {pid}",
        }
        for v in values
    ]
    patch = {
        kind: {
            "parameter_id": pid,
            "by": by,
            "copies_by_condition": {c: copy_of[value_of[c]] for c in conds},
        }
    }
    return {"on_assembly_patch": patch, "adds_parameters": adds}, []


def override_value(v):
    """A condition override value as the engine renders it: a float or a parameter id.

    A parameter id is the condition's own copy of a model parameter. Anything else
    raises ValueError by name, so a typo never becomes a silent zero.
    """
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    try:
        return float(s)
    except ValueError:
        pass
    if TOKEN.fullmatch(s):
        return s
    raise ValueError(
        f"condition override value {v!r} is neither a number nor a parameter id"
    )


# The falsy spellings a reply uses for "this condition does not pre-equilibrate".
_NO_PREEQUILIBRATION = (None, False, 0, "", "false", "no", "none")


def preequilibration_overrides(value) -> dict | None:
    """A condition's `preequilibration` declaration as the overrides it renders.

    None when the condition does not pre-equilibrate. A dict is the
    pre-equilibration condition's own overrides, applied on top of a copy of
    the measured condition; its values normalise as overrides do. Anything else
    that is truthy (a bare `true`, a label, a list) or an empty dict names no
    condition, and raises ValueError with the sentence the agent is re-asked
    with: only the agent knows which overrides remove the stimulus.
    """
    if isinstance(value, str) and value.strip().lower() in _NO_PREEQUILIBRATION:
        return None
    if not isinstance(value, dict) and value in _NO_PREEQUILIBRATION:
        return None
    if not isinstance(value, dict) or not value:
        raise ValueError(
            f"preequilibration is {value!r} — say which overrides form the "
            f"pre-equilibration condition: a dict of them, applied on top of "
            f"this condition's own overrides (the measured condition with the "
            f'stimulus removed, e.g. {{"S": 0}}; a control whose stimulus is '
            f"already off repeats that override), or false for none"
        )
    return {str(k): override_value(v) for k, v in value.items()}


def _preequilibration_form(value):
    """What a declaration compares as: its overrides, else the raw value."""
    try:
        return preequilibration_overrides(value)
    except ValueError:
        return repr(value)


def _condition_class_problems(args: dict, assembly: dict) -> list[str]:
    cid = _resolve_condition(args, assembly, strict=True)
    cur = next(c for c in assembly.get("conditions", []) if c["condition_id"] == cid)
    cur_ov = cur.get("overrides") or {}
    problems = []
    # any change counts: switching it on or off, or changing which overrides
    # form the pre-equilibration condition
    if "preequilibration" in args and _preequilibration_form(
        args["preequilibration"]
    ) != _preequilibration_form(cur.get("preequilibration")):
        problems.append(
            "change_condition: changing pre-equilibration on "
            "a measured condition reinterprets the data — route "
            "through S2 or a human decision, not the search"
        )
    for k, v in (args.get("overrides") or {}).items():
        # an id compares as an id, not through float()
        if (
            k in cur_ov
            and v is not None
            and override_value(v) != override_value(cur_ov[k])
        ):
            problems.append(
                f"change_condition: override {k!r} already "
                f"encodes a measured factor ({cur_ov[k]}); changing its "
                f"VALUE reinterprets the data — refused (hypothesis-class "
                f"axes add/remove which parameter a perturbation enters)"
            )
    return problems


def _resolve_observable(args: dict, assembly: dict, strict: bool) -> str | None:
    ids = {o["observable_id"] for o in assembly.get("observables", [])}
    if args.get("observable_id"):
        if args["observable_id"] in ids:
            return args["observable_id"]
        if strict:
            raise ValueError(
                f"observable_id {args['observable_id']!r} is not in the "
                f"assembly (have {sorted(ids)})"
            )
        return None
    label = args.get("observable_label")
    hits = [
        o["observable_id"]
        for o in assembly.get("observables", [])
        if str(o.get("maps_to_label")) == str(label)
    ]
    if len(hits) == 1:
        return hits[0]
    if strict:
        raise ValueError(
            f"observable_label {label!r} resolves to {hits or 'nothing'} "
            f"in the assembly (labels: "
            f"{sorted(str(o.get('maps_to_label')) for o in assembly.get('observables', []))})"
        )
    return None


def _resolve_condition(args: dict, assembly: dict, strict: bool) -> str | None:
    ids = {c["condition_id"] for c in assembly.get("conditions", [])}
    if args.get("condition_id"):
        if args["condition_id"] in ids:
            return args["condition_id"]
        if strict:
            raise ValueError(
                f"condition_id {args['condition_id']!r} is not in the "
                f"assembly (have {sorted(ids)})"
            )
        return None
    label = args.get("condition_label")
    hits = [
        c["condition_id"]
        for c in assembly.get("conditions", [])
        if str(c.get("maps_to_label")) == str(label)
    ]
    if len(hits) == 1:
        return hits[0]
    if strict:
        raise ValueError(f"condition_label {label!r} resolves to {hits or 'nothing'}")
    return None


def resolve_refs(patch: dict, assembly: dict) -> dict:
    """A copy of the patch with labels turned into assembly ids. ValueError
    when a reference does not resolve — never a downstream SimError."""
    kind, args = patch_kind(patch)
    args = dict(args)
    if kind == "split_parameter":
        return {kind: args}  # condition ids already, written by resolve_split
    if kind in OBSERVABLE_KINDS:
        if kind == "change_scaling" and args.get("observable_ids"):
            args["observable_ids"] = [
                (
                    _resolve_observable({"observable_id": x}, assembly, strict=True)
                    if x
                    in {o["observable_id"] for o in assembly.get("observables", [])}
                    else _resolve_observable(
                        {"observable_label": x}, assembly, strict=True
                    )
                )
                for x in args["observable_ids"]
            ]
        else:
            args["observable_id"] = _resolve_observable(args, assembly, strict=True)
    else:
        args["condition_id"] = _resolve_condition(args, assembly, strict=True)
    return {kind: args}


def apply_patch(asm: dict, patch: dict) -> dict:
    """Apply one patch to a copy of the assembly; references must already be ids."""
    asm = copy.deepcopy(asm)
    kind, args = patch_kind(patch)
    if kind == "change_observable_formula":
        for o in asm["observables"]:
            if o["observable_id"] == args["observable_id"]:
                # the AMICI-safe spelling the base formulas get; an unknown
                # function raises by name
                o["formula"] = amici_safe_formula(str(args["new_formula"]))
    elif kind == "change_transformation":
        for o in asm["observables"]:
            if o["observable_id"] == args["observable_id"]:
                o["transformation"] = str(args["new"])
    elif kind == "change_noise_model":
        for n in asm["noise"]:
            if n["observable_id"] == args["observable_id"]:
                if "new_distribution" in args:
                    n["distribution"] = str(args["new_distribution"])
                if "new_formula" in args:
                    n["formula"] = amici_safe_formula(str(args["new_formula"]))
                if "new_per" in args:
                    n["per"] = str(args["new_per"])
    elif kind == "add_offset":
        for s in asm["scaling"]:
            if s["observable_id"] == args["observable_id"]:
                s["mode"] = {
                    "factor": "factor_offset",
                    "factor_offset": "factor_offset",
                }.get(s.get("mode"), "offset")
                if not s.get("offset_parameter"):
                    s["offset_parameter"] = f"off_{args['observable_id']}"
    elif kind == "remove_scaling":
        for s in asm["scaling"]:
            if s["observable_id"] == args["observable_id"]:
                s["mode"] = (
                    "offset" if s.get("mode") in ("factor_offset", "offset") else "none"
                )
    elif kind == "change_scaling":
        targets = set(args.get("observable_ids") or [args["observable_id"]])
        shared = args.get("shared_across_observables", False) or False
        for s in asm["scaling"]:
            if s["observable_id"] not in targets:
                continue
            s["per"] = str(args["per"])
            s["shared_across_observables"] = shared
            s["pin_first_to_one"] = bool(args.get("pin_first_to_one", False))
            # a per-timepoint or per-condition factor IS a factor: an observable
            # that had none gains one, one that had an offset keeps it
            if s.get("mode") in (None, "", "none"):
                s["mode"] = "factor"
            elif s.get("mode") == "offset":
                s["mode"] = "factor_offset"
            if args.get("mode"):
                s["mode"] = str(args["mode"])
            # the parameter STEM: the group's name when shared, else the observable's
            s["scale_parameter"] = (
                f"sc_{shared}"
                if shared
                else (s.get("scale_parameter") or f"sc_{s['observable_id']}")
            )
    elif kind == "split_parameter":
        copies = args.get("copies_by_condition") or {}
        for c in asm["conditions"]:
            cp = copies.get(c["condition_id"])
            if cp:
                c["overrides"] = {
                    **(c.get("overrides") or {}),
                    args["parameter_id"]: cp,
                }
    elif kind == "change_condition":
        for c in asm["conditions"]:
            if c["condition_id"] == args["condition_id"]:
                ov = dict(c.get("overrides") or {})
                for k, v in (args.get("overrides") or {}).items():
                    if v is None:
                        ov.pop(k, None)
                    else:
                        ov[k] = override_value(v)  # a parameter id stays an id
                c["overrides"] = ov
    return asm


def apply_overlay(
    asm: dict, overlay: list[dict], assembly_for_refs: dict | None = None
) -> dict:
    """Apply an ordered list of patches (labels resolved against
    `assembly_for_refs`, default the assembly itself)."""
    base = assembly_for_refs if assembly_for_refs is not None else asm
    for patch in overlay or []:
        asm = apply_patch(asm, resolve_refs(patch, base))
    return asm


# The revision loop's assembly-side moves, as patches.
MOVE_TO_PATCH = {
    "change_noise_model": lambda a: {
        "change_noise_model": {
            "observable_id": a["observable_id"],
            "new_distribution": a["new_distribution"],
            **({"new_formula": a["new_formula"]} if a.get("new_formula") else {}),
            **({"new_per": a["new_per"]} if a.get("new_per") else {}),
        }
    },
    "add_offset": lambda a: {"add_offset": {"observable_id": a["observable_id"]}},
    "remove_scaling": lambda a: {
        "remove_scaling": {"observable_id": a["observable_id"]}
    },
    "change_observable_formula": lambda a: {
        "change_observable_formula": {
            "observable_id": a["observable_id"],
            "new_formula": a["new_formula"],
        }
    },
}


def apply_move(asm: dict, move: dict) -> dict:
    """Apply a revision-loop move through `apply_patch`; other moves return a copy."""
    t = move.get("type")
    if t not in MOVE_TO_PATCH:
        return copy.deepcopy(asm)
    return apply_patch(asm, MOVE_TO_PATCH[t](move.get("args", {})))
