"""Deterministic source caching for retrieved evidence.

The research agent's claims are snapshots; this caches the DOCUMENTS the
claims point at, so audits ("does the source actually say that") and reruns
survive web rot. Engine-side and deterministic on purpose: no agent decides
what gets cached, and every outcome (cached / paywalled / unreachable) is
recorded per item. Beside it, two lookups the engine makes of a cited
source, never an agent: does its identifier exist (`resolve_source`), and
what kind of publication is it (`publication_types`).

Cache lives inside the run (runs/ is gitignored): source documents are for
local audit, never for committing to a shared repository.
"""

from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.request
from pathlib import Path

_MAX_BYTES = 20 * 1024 * 1024
_TIMEOUT_S = 20
_EXT = {
    "application/pdf": ".pdf",
    "text/html": ".html",
    "text/plain": ".txt",
    "application/xml": ".xml",
    "text/xml": ".xml",
}


def cache_source(url: str, out_dir: Path, base_dir: Path | None = None) -> dict:
    """Fetch one URL into out_dir. Returns a status record, never raises.

    `file:` URLs are accepted so a FIXTURE can exercise this path with no
    network: a relative `file:./sources/x.txt` resolves against
    `base_dir` (the testcase directory). A live research reply never yields
    file URLs; caching a local file is harmless if one ever does."""
    from octomod.workflow_modules.knowledge.supplied_literature import case_document

    rel = case_document(url)
    if rel is not None:
        # a case's own document, `file:./paper/x.pdf`, read against base_dir
        url = (Path(base_dir or ".") / rel).resolve().as_uri()
    if not url or not url.startswith(("http://", "https://", "file://")):
        return {"fetch_status": "no-url"}
    out_dir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "octomod/0.1 (source audit cache; academic use)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = resp.read(_MAX_BYTES + 1)
            if len(data) > _MAX_BYTES:
                return {"fetch_status": "too-large"}
            ctype = (resp.headers.get_content_type() or "").lower()
    except Exception as e:
        return {"fetch_status": f"unreachable: {type(e).__name__}"}
    sha = hashlib.sha256(data).hexdigest()[:16]
    path = out_dir / f"{sha}{_EXT.get(ctype, '.bin')}"
    path.write_bytes(data)
    return {
        "fetch_status": "cached",
        "cached_file": path.name,
        "sha256": sha,
        "content_type": ctype,
        "bytes": len(data),
    }


_DOI_RE = None


def resolve_source(source: str) -> str:
    """Deterministic hallucination trap: does this identifier exist?
    Returns 'resolved' | 'unresolvable' | 'not-checkable' (general knowledge,
    book without ISBN lookup, etc.) | 'unchecked: <err>' (network trouble —
    never punished as fabrication)."""
    import re

    global _DOI_RE
    if _DOI_RE is None:
        _DOI_RE = re.compile(r"10\.\d{4,9}/\S+")

    s = (source or "").strip()
    low = s.lower()
    if not s or any(
        k in low for k in ("general knowledge", "none", "textbook", "assumed", "n/a")
    ):
        return "not-checkable"
    m = _DOI_RE.search(s)
    url = None
    if m:
        # registry-level handle lookup: answers "does this DOI exist" without
        # touching the publisher (whose bot-walls would read as 'unchecked')
        url = "https://doi.org/api/handles/" + m.group(0).rstrip(".,;)")
    elif low.startswith("pmid"):
        digits = "".join(ch for ch in s if ch.isdigit())
        if digits:
            url = (
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                f"?db=pubmed&id={digits}&retmode=json"
            )
    elif s.startswith(("http://", "https://")):
        url = s
    if url is None:
        return "not-checkable"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "octomod/0.1 (citation resolution; academic use)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read(4096) if "eutils" in url else b""
            if "eutils" in url and b'"error"' in body.lower():
                return "unresolvable"
            return "resolved" if resp.status < 400 else "unresolvable"
    except urllib.error.HTTPError as e:
        return "unresolvable" if e.code in (404, 410) else f"unchecked: HTTP {e.code}"
    except Exception as e:
        return f"unchecked: {type(e).__name__}"


_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_PUB_DOI = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+")
_PUB_PMID = re.compile(r"(?:pmid\D{0,3}|pubmed\.ncbi\.nlm\.nih\.gov/)(\d{4,9})", re.I)
# answers already looked up in this process, by identifier; a lookup that
# failed is not kept, so a later call may succeed
_PUBLICATION_TYPES: dict[str, list[str]] = {}


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "octomod/0.1 (publication type lookup; academic use)"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read(1024 * 1024)


def publication_types(source, *, fetch=None) -> list[str] | None:
    """PubMed's publication types of the paper a source names ("Review",
    "Journal Article", …), for the engine's own reading of what a source is.

    `source` is any text holding a DOI or a PMID — a source string, a URL, or
    an evidence item (its `source` and `url`). A DOI is looked up to its PMID
    first (E-utilities esearch), then the PMID's summary gives `pubtype`
    (esummary). None when the source names neither, when PubMed does not know
    it, or on any network trouble: a type nobody could look up is never held
    against a source. `fetch(url) -> bytes | str` replaces the network, for
    tests."""
    import json
    import urllib.parse

    if isinstance(source, dict):
        source = " ".join(str(source.get(k) or "") for k in ("source", "url"))
    text = str(source or "")
    doi = _PUB_DOI.search(text)
    pmid = _PUB_PMID.search(text)
    if doi:
        key = "doi:" + doi.group(0).rstrip(".,;)").lower()
    elif pmid:
        key = "pmid:" + pmid.group(1)
    else:
        return None
    if key in _PUBLICATION_TYPES:
        return list(_PUBLICATION_TYPES[key])
    get = fetch or _fetch

    def as_json(url: str) -> dict:
        body = get(url)
        return json.loads(body.decode() if isinstance(body, bytes) else body)

    try:
        if key.startswith("doi:"):
            term = urllib.parse.quote(f"{key[4:]}[doi]", safe="")
            found = as_json(
                f"{_EUTILS}/esearch.fcgi?db=pubmed&term={term}&retmode=json"
            )
            ids = (found.get("esearchresult") or {}).get("idlist") or []
            if not ids:
                return None
            pm = str(ids[0])
        else:
            pm = key[5:]
        summary = as_json(f"{_EUTILS}/esummary.fcgi?db=pubmed&id={pm}&retmode=json")
        record = (summary.get("result") or {}).get(pm)
        if not isinstance(record, dict) or "error" in record:
            return None
        types = [str(t) for t in record.get("pubtype") or [] if str(t).strip()]
    except Exception:
        return None
    _PUBLICATION_TYPES[key] = types
    return list(types)
