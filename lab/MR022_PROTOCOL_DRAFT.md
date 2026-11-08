# MR-022 draft protocol for Lyra

**AWAITING_LYRA.** This is a candidate data source and a proposed evaluation procedure. Hypothesis, model, minimum useful effect, and execution approval remain undecided.

## Candidate data

AqSolDB v1.0, Sorkun, Khetan and Er (2019), is a Harvard Dataverse release. The NLM catalogue records CC0 1.0 for the deposited dataset. Cite the authors and the deposit DOI when using it. [Publisher release](https://www.amdlab.nl/database/AqSolDB/) · [Harvard Dataverse deposit](https://doi.org/10.7910/DVN/OVHAW8) · [NLM rights record](https://datasetcatalog.nlm.nih.gov/dataset?q=0000042260)

The data descriptor reports 9,982 unique compounds from nine source datasets. The deposited CSV is approximately 3.6 MB. The published schema describes 26 variables, including SMILES and InChIKey, experimental aqueous solubility as log10(mol/L), aggregation fields and computed 2D descriptors. These are published counts and units. No dataset bytes were downloaded in this preparation. [Original data descriptor and schema](https://pmc.ncbi.nlm.nih.gov/articles/PMC6687799/#Tab2)

Measurements were harmonized across sources with heterogeneous assay conditions and solubility definitions. The published row schema lacks standardized per-row pH, temperature and assay type. The authors used model-based arbitration for some conflicting observations. Evaluate against the deposited labels only. A within-release holdout cannot establish performance in an independent laboratory or under a standardized assay. If the intended question requires controlled conditions, select a different dataset before approval. [AqSolDB curation](https://pmc.ncbi.nlm.nih.gov/articles/PMC6687799/) · [Study of measurement definitions](https://pmc.ncbi.nlm.nih.gov/articles/PMC10948805/)

## Proposed evaluation for review

| Item | Draft procedure |
| --- | --- |
| Target | Deposited `Solubility`, in log10(mol/L), under the release's documented measurement mixture. |
| Eligibility | Freeze the handling of invalid structures, missing or non-finite labels, salts, stereochemistry and duplicates. Report exclusions. Keep source and identity metadata for auditing only. |
| Split | Allocate approximately 80% to training and 20% to holdout by disjoint canonical molecular scaffold groups. Freeze the algorithm, version, seed, and handling of acyclic compounds before computing. Check both structural identity and group overlap. Fit preprocessing and select parameters using training groups only. |
| Baseline | Constant median of eligible training logS. |
| Negative control | Refit the candidate procedure with one fixed, preregistered permutation of training labels. Score on the original holdout labels and compare with the baseline. |
| Metric and uncertainty | Report held-out MAE for baseline, candidate and negative control in log10(mol/L). Report paired MAE improvement as baseline minus candidate with a 95% interval from a seeded bootstrap over held-out scaffold groups. Freeze the bootstrap repetitions, decision threshold and treatment of invalid intervals before opening the holdout. |
| Leakage protection | Exclude target-derived fields such as `SD`, `Occurrences` and `Group` from model inputs. Exclude raw identifiers and source IDs from predictors. Freeze the allowed structure-derived descriptors or representation before fitting. |

## Admission and execution

1. Lyra decides the question, minimum useful effect, model, control criterion and whether the dataset's conditions and rights meet the purpose. Record the result of the review.
2. If approved, pin the official deposit version and file ID and fetch the original-format bytes from Dataverse. Verify byte size, schema and release metadata, record SHA-256 locally, and append the frozen protocol and provenance through MR-014 before analysis.
3. Exercise the MR-005 protections using synthetic records for split overlap, target leakage, missing labels and failed controls. The current synthetic gate supplies engineering evidence only. The experimental admission decision remains with Lyra.
4. Use the existing MR-006 offline stages for input and split verification, computation and control review. Pin inputs, environment, seeds and implementation. Store aggregate evidence and the independent review status in MR-014, including a null or negative result.

No model fit, holdout evaluation, or scientific claim is authorized by this draft. The file ID, original byte count and SHA-256 are open until acquisition is approved.
