# MR-021.3 · Scientific discovery

Read [Issue #10](https://github.com/Monisarek/morpheus-project/issues/10), the [research strategy](https://github.com/Monisarek/morpheus-project/pull/4), and the project discovery skill. Existing `ocon9000 catalog` describes the known EEG source; the Toolbox had no literature discovery tool. This change extends the Toolbox and the MR-005 quality gate. The local unfinished LAB runner is outside this branch. No new runner or scheduler is required.

| Source | State and bounds |
|---|---|
| [Europe PMC REST](https://dev.europepmc.org/RestfulWebService) | Two public metadata GETs, three hits per lane. Titles, abstracts and provider links are discarded. Correction/retraction indicators are flagged when supplied. Otherwise integrity is UNKNOWN |
| [DataCite](https://api.datacite.org/dois/10.5281/zenodo.22145442) | One public DOI metadata GET for a reviewed candidate. DOI and dataset type must agree. The provider's license field is not a DUA or a transfer approval |
| [PubMed MCP](https://www.ncbi.nlm.nih.gov/books/NBK25501/) | Existing read-only search used from Codex, with a two-record limit. Workflow documented in the skill. No new MCP server or token |
| [Official OpenAlex MCP](https://help.openalex.org/access/connector/) | Streamable HTTP with OAuth. The [provider documents a free account budget](https://help.openalex.org/access/pricing/). Owner login, actual tool inventory and available quota were not verified, so it remains disabled |

Only a reviewed topic enum crosses the network. Hosts, paths and requests are fixed. Redirects are refused. Per-request timeout is eight seconds, body limit 512 KiB. A 429 or a response with Retry-After stops that lookup, and 502/503/504 without Retry-After get at most one retry. Local reports use the existing ignored `.morpheus/tool_runs` directory. Cache reuse for network evidence is disabled.

```powershell
py -m morpheus_tools find discovery
py -m morpheus_tools describe science.discovery
$result = py -m morpheus_tools run science.discovery --topic propofol-eeg | ConvertFrom-Json
py -m morpheus_tools.quality_gate --preflight $result.report_path
```

Discovery returns exit 3 for a partial matrix and preflight returns exit 2 for NO_GO. The current preflight deliberately has no real-data GO path. Assertions in a local report cannot satisfy human gates. Existing synthetic MR-005 evaluation is unchanged.

## Live smoke evidence

Question for discovery only: could past EEG provide information about behavioral responsiveness during propofol sedation beyond a clinical comparator? Look for confounding, observation effects and signal artifacts as competing explanations.

- Europe PMC returned two bounded pages, 3/4,445 and 3/2,876 at retrieval, with five unique records after DOI/PMID deduplication. Examples [initial](https://doi.org/10.1016/j.bja.2026.03.082) and [seen in both lanes](https://doi.org/10.1186/s12871-026-04125-y). The lanes record search provenance rather than study verdicts.
- PubMed MCP returned 2 of 16 matches for public terms. One candidate for reading is [PMID 19690246](https://pubmed.ncbi.nlm.nih.gov/19690246/). Search relevance and study methods require review.
- The [DataCite record](https://api.datacite.org/dois/10.5281/zenodo.22145442) returned dataset metadata and CC BY 4.0, with version absent. Preflight returned NO_GO because DUA, person-level split, timing, target and other gates remain unverified. No data or full text was fetched and no scientific effect was inferred.

Direct paid API charges were $0. Account or shared provider quota consumption was not measured. E25 remains OPEN. Future integrations require a concrete research need and verified free use.
