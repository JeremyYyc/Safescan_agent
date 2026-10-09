# Data collection

最新中文入口：[采集流程与结果总览](README.zh-CN.md)。该文档说明学生公寓、社会公寓和维修图片的采集、整理、交付路径及最终数量。

以下保留早期试采的运行说明。

## NSW collection pilot

Run from the repository root with Python 3.11+:

```powershell
python -m pip install -r scripts/data_collection/requirements.txt
python scripts/data_collection/collect.py --dry-run
python scripts/data_collection/collect.py
python -m unittest discover -s scripts/data_collection -p test_collect.py -v
```

To retry only selected sources, repeat `--source <source-id>`. Do not retry a
blocked source until its access conditions have been reviewed. A 403 or 429 stops
that host for the current run; it does not create a persistent cross-run block.

The default output is `data/collection-pilot/<UTC-run-id>/`, ignored by Git:

- `raw/`: HTML snapshots and successful robots.txt responses.
- `documents.jsonl`: structured text, heading paths, links and provenance.
- `summary.json`: successes, failures, byte/request counts and new versions.
- `../index.json`: stable source IDs and unique extracted-text hashes across runs.

Each run retains its own snapshot, including unchanged documents. The shared
index does not create another content version for an unchanged source. Changes
to extraction logic can create new text versions even when the raw page is unchanged;
inspect `raw_sha256` and `extractor_version` when comparing versions.
Run one collector at a time: the local index is not a concurrent database.

Exit code 1 means at least one source failed; successful documents remain usable
for review. A non-200 robots response prevents collection of that source. Each
redirect is allowlisted and checked against loaded robots rules before fetching;
a redirect to a host whose robots rules have not been loaded is rejected.
PDFs are recorded as pending/unsupported rather than parsed as HTML.

Documents remain `pending_review` and are never automatically published. Website
dates are source metadata, not verified legal effective dates. The NSW Government
[copyright policy](https://www.nsw.gov.au/nsw-government/about-website/copyright)
states a general CC BY 4.0 licence with exceptions for specified content, third-party
material and branding. Check document-specific notices before reuse; do not treat
the entire HTML snapshot, including logos, as unrestricted content.

Limits: HTTPS allowlist, 30 network attempts, 50 MiB per run, 5 MiB per response,
20-second HTTP operation timeout, at least 2 seconds between requests per host,
at most 2 retries for transport/server errors, and 5 redirect hops. On 429 the
collector stops instead of retrying before Retry-After. This is a fixed-list HTML
collector, not a recursive crawler or a knowledge-service ingestion worker.

Fixtures in tests are synthetic. No production database, object store or model API
is contacted. See `docs/DATA-COLLECTION-PILOT.zh-CN.md` for the broader plan.

## Housing sample

`housing_collect.py` collects a fixed UniLodge sample, separately from the NSW
knowledge collector. It parses building and room-type records, downloads at most
16 explicitly associated photos with `--download-media`, and preserves external
Matterport links without downloading their models or videos. Use `--process DIR`
to rebuild saved data and an HTML preview offline. The optional media downloader
reuses already verified local files within that directory.

See `docs/HOUSING-DATA-PILOT.zh-CN.md` for actual counts, source selection, missing
fields, validation, and scaling prerequisites. The pilot is room-type data, not
confirmed vacant-unit inventory. No common legal ownership or open media licence
is inferred from the common source website.
