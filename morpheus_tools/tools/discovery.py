"""Bounded public bibliographic and dataset metadata. No arbitrary outbound text."""

from datetime import datetime, timezone
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


EUROPE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
DATASET = "10.5281/zenodo.22145442"
DATACITE = "https://api.datacite.org/dois/" + DATASET
LIMIT = 3
MAX_RESPONSE = 512 * 1024
DOI = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9]{1,110}", re.I | re.ASCII)
PMID = re.compile(r"[1-9][0-9]{0,11}", re.ASCII)
DATE = re.compile(r"\d{4}(?:-\d{2}-\d{2})?", re.ASCII)
QUERIES = {
    "initial": "propofol AND EEG AND (responsiveness OR sedation)",
    "counterevidence": "propofol AND EEG AND (responsiveness OR sedation) AND (limitations OR artifact OR confounding)",
}
RIGHTS = {"cc-by-4.0", "cc0-1.0", "cc-by-nc-4.0", "cc-by-sa-4.0"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url):
    target = urlsplit(url)
    if not (url == DATACITE or (
        target.scheme == "https" and target.netloc == "www.ebi.ac.uk"
        and target.path == urlsplit(EUROPE).path and not target.fragment
        and target.query in {search_url(query).split("?", 1)[1] for query in QUERIES.values()}
    )):
        raise ValueError("source_not_allowlisted")
    opener = build_opener(NoRedirect())
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "MORPHEUS-Metadata/1.0"})
    for attempt in range(2):
        try:
            with opener.open(request, timeout=8) as response:
                raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise ValueError("source_response_too_large")
            return json.loads(raw)
        except HTTPError as exc:
            code, deferred = exc.code, exc.headers.get("Retry-After")
            exc.close()
            if not attempt and code in (502, 503, 504) and not deferred:
                continue
            raise ValueError("source_rate_limited" if code == 429 else "source_http_error") from None


def search_url(query):
    return EUROPE + "?" + urlencode({
        "query": query, "format": "json", "resultType": "core", "pageSize": LIMIT,
    })


def identifier(value, pattern):
    return value.lower() if isinstance(value, str) and pattern.fullmatch(value) else None


def papers(payload):
    rows = payload["resultList"]["result"]
    total = payload["hitCount"]
    if type(total) is not int or total < len(rows) or not isinstance(rows, list) or len(rows) > LIMIT:
        raise ValueError("invalid_literature_page")
    result = []
    for row in rows:
        doi = identifier(row.get("doi"), DOI)
        pmid = identifier(row.get("pmid"), PMID)
        if not (doi or pmid):
            continue
        types = str(row.get("pubTypeList", "")).lower()[:1000]
        updates = str(row.get("commentCorrectionList", "")).lower()[:2000]
        integrity = ("FLAGGED" if row.get("isRetracted") in ("Y", True)
                     or any(word in types + updates for word in ("retract", "erratum", "correct", "expression of concern"))
                     else "UNKNOWN")
        result.append({
            "doi": doi, "pmid": pmid, "integrity": integrity,
            "citation": "https://doi.org/" + doi if doi else "https://pubmed.ncbi.nlm.nih.gov/" + pmid + "/",
            "date": identifier(row.get("firstPublicationDate"), DATE),
            "version": "UNKNOWN", "searchable": True,
            "retrievable": "UNKNOWN", "license": "UNKNOWN", "external_llm": "DENIED",
        })
    return result, total, len(rows)


def dataset(payload):
    attrs = payload["data"]["attributes"]
    if identifier(attrs.get("doi"), DOI) != DATASET or attrs["types"]["resourceTypeGeneral"] != "Dataset":
        raise ValueError("dataset_identity_or_type_mismatch")
    rights = {row.get("rightsIdentifier", "").lower() for row in attrs.get("rightsList", [])}
    license_id = next(iter(rights)) if len(rights) == 1 and rights <= RIGHTS else "UNKNOWN"
    version = attrs.get("version")
    version = version if isinstance(version, str) and re.fullmatch(r"v?[0-9]+(?:\.[0-9]+){0,3}", version, re.ASCII) else "UNKNOWN"
    return {
        "doi": DATASET, "citation": "https://doi.org/" + DATASET, "version": version,
        "date": identifier(str(attrs.get("publicationYear")), DATE),
        "searchable": True, "retrievable": "UNKNOWN", "license": license_id,
        "dua": "UNKNOWN", "person_split": "UNKNOWN", "timestamps": "UNKNOWN", "target": "UNKNOWN",
        "scope": "UNKNOWN", "baseline": "UNKNOWN", "schema": "UNKNOWN",
        "external_llm": "DENIED",
    }


def _merge(results, row, lane):
    matched = [item for item in results if any(row[key] and row[key] == item[key] for key in ("doi", "pmid"))]
    row["lanes"] = sorted({lane, *(value for item in matched for value in item["lanes"])})
    for item in matched:
        for key in ("doi", "pmid"):
            if row[key] and item[key] and row[key] != item[key]:
                row["integrity"] = "FLAGGED"
            row[key] = row[key] or item[key]
        if item["integrity"] == "FLAGGED":
            row["integrity"] = "FLAGGED"
        results.remove(item)
    row["citation"] = "https://doi.org/" + row["doi"] if row["doi"] else row["citation"]
    results.append(row)


def add_arguments(parser, operation):
    parser.add_argument("--topic", required=True, choices=("propofol-eeg",))


def execute(args, operation):
    if args.topic != "propofol-eeg":
        raise ValueError("unreviewed_public_topic")
    records, pages = [], {}
    for lane, query in QUERIES.items():
        try:
            rows, total, retrieved = papers(fetch(search_url(query)))
            pages[lane] = {"total": total, "retrieved": retrieved,
                           "complete": total == retrieved == len(rows)}
            for row in rows:
                _merge(records, row, lane)
        except (OSError, KeyError, TypeError, ValueError, AttributeError, RecursionError) as exc:
            pages[lane] = {"complete": False, "error": _failure(exc)}
    try:
        candidate = dataset(fetch(DATACITE))
    except (OSError, KeyError, TypeError, ValueError, AttributeError, RecursionError) as exc:
        candidate = {"doi": DATASET, "citation": "https://doi.org/" + DATASET,
                     "searchable": "UNKNOWN", "error": _failure(exc), "external_llm": "DENIED"}
    partial = not all(page["complete"] for page in pages.values()) or "error" in candidate
    return {
        "status": "partial" if partial else "ok",
        "summary": f"{len(records)} unique bibliographic records; dataset metadata only; NO-GO for execution",
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "papers": records, "literature_pages": pages, "dataset": candidate,
        "sources": {"literature": EUROPE, "dataset": DATACITE},
    }


def _failure(error):
    return "source_rate_limited" if str(error) == "source_rate_limited" else "source_unverified"


def preflight(report):
    reasons = ["real_data_admission_unverified", "independent_review_unverified",
               "preregistration_unverified", "MR-004/005/006/015_real_run_acceptance_unverified"]
    if not isinstance(report, dict) or report.get("tool") != "science.discovery":
        return {"status": "NO_GO", "blockers": ["missing_discovery_report", *reasons]}
    candidate = report.get("dataset")
    if not isinstance(candidate, dict) or candidate.get("doi") != DATASET or "error" in candidate:
        reasons.append("dataset_identity_unverified")
    else:
        for field in ("version", "license", "dua", "person_split", "timestamps", "target", "scope", "baseline", "schema"):
            if field in ("dua", "person_split", "timestamps", "target", "scope", "baseline", "schema") or candidate.get(field) in (None, "UNKNOWN"):
                reasons.append(field + "_unverified")
    if report.get("status") != "ok" or not report.get("papers"):
        reasons.append("literature_incomplete")
    return {"status": "NO_GO", "blockers": reasons}
