# Offline housing quality audit

No HTTP requests, media downloads, backend imports or production release. Reads the two frozen datasets in `cohort.json`; writes only to a new output directory. Existing output directories are rejected.

```powershell
python -m unittest discover -s scripts/data_analysis -p "test_*.py"
python -X utf8 scripts/data_analysis/baseline.py --output data/collection-pilot/analysis-final
python -X utf8 scripts/data_analysis/baseline.py --output data/collection-pilot/analysis-replay
python scripts/data_analysis/verify_run.py data/collection-pilot/analysis-final --compare data/collection-pilot/analysis-replay
```

Uses existing `beautifulsoup4` and `Pillow` dependencies from `scripts/data_collection/requirements.txt`; SQLite is Python standard library. Historical data directories must be present locally; they are not included in Git. Tests use generated fixtures, not copyrighted images, and require no network.

Outputs: normalized JSON, per-sample checks, source registry, before/after metrics, source-level breakdown, Markdown report and SQLite database. `manifest.json` records source files, configuration, code hash, Git state and output hashes. Output data stays under the ignored collection directory.

The analysis deliberately distinguishes identity completeness from room-parameter completeness. Unknown price basis and lease conditions remain null. Room-type samples and concrete unit offers have separate denominators. Image uniqueness uses actual content SHA-256.

`home_reviews.json` contains assistant visual suggestions bound to exact image hashes. It cannot grant human approval or usage rights. Strict verified-media coverage remains zero until a separate human review is recorded. A low-resolution floorplan does not pass the readability gate.

`flagstaff_candidates.json` is a separate research queue, not collected data; it does not enter the retrospective audit denominator. No historical request success or labour cost is inferred from incomplete logs.

## Source-fit experiment (separate cohort)

`source_fit.py` reads the frozen Flagstaff, Novus and media probes plus the actual Property model and parking migration. It creates two evidence samples, explicitly synthetic projections, a contract-subset validation report and input/output hashes. It reparses HOME index cards with the corrected selector. It does not alter the historical baseline or import records into any database.

```powershell
python -X utf8 scripts/data_analysis/source_fit.py --output data/collection-pilot/source-fit-replay
```

Media hash, decoding, dimensions and review membership are checked. `source_fit_reviews.json` records assistant visual observations, not independent human approval. Missing currency and UniLodge parking remain unknown in the evidence layer; demonstration assumptions are enumerated separately. External VR/video links do not satisfy the inspection file contract. These artifacts are not API request bodies, a complete database constraint validator, or a reuse license.

## UniLodge acceptance dashboard

`unilodge_acceptance.py --output <new-directory>` validates the v2 Flagstaff snapshot and emits offline `index.html`, `acceptance.json` and `manifest.json`. The HTML includes coverage, media composition, per-room gaps, historical offer comparison and filterable local image evidence. No additional HTTP requests are made. Review categories are bound to the media outcomes hash in `unilodge_acceptance_reviews.json`; changing the snapshot requires a new review.

The conservative core package is one complete layout, two people-free interior candidates and a current offer. This is a technical sample gate, not production approval or safety evidence. Room-type, offer and image denominators remain separate.
