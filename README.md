# Google Maps Lead Pipeline

[![tests](https://github.com/YassinWael/Google-maps-lead-generator/actions/workflows/tests.yml/badge.svg)](https://github.com/YassinWael/Google-maps-lead-generator/actions/workflows/tests.yml)

A small Python pipeline that turns Google Places text searches into normalized,
deduplicated CSV and JSON datasets. It handles pagination, transient request
failures, optional website enrichment, and deterministic exports.

This is a sanitized public version of a lead-research workflow. It contains no
client data, API keys, cookies, or generated lead files.

Licensed under the [MIT License](LICENSE).

## What it demonstrates

- Source-specific API integration with an explicit response field mask
- Pagination with `nextPageToken` / `pageToken`
- Retry and exponential-backoff handling for transient failures
- Normalization into a stable output schema
- Cross-query deduplication by Google Place ID
- Optional HTML metadata extraction from business websites
- CSV and JSON delivery with automated tests

## Pipeline

```text
search queries
    -> Google Places Text Search API
    -> paginate and validate JSON responses
    -> normalize records
    -> deduplicate and filter
    -> optionally enrich website metadata
    -> leads.json + leads.csv
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Set `GOOGLE_MAPS_API_KEY` in `.env`, then run:

```bash
python main.py \
  --query "independent pharmacy in Dammam" \
  --query "medical clinic in Khobar" \
  --pages 2 \
  --min-rating 4.0 \
  --min-reviews 10 \
  --enrich-websites
```

Outputs are written to `output/leads.json` and `output/leads.csv` by default.

## Output schema

```json
{
  "place_id": "ChIJ...",
  "name": "Example Clinic",
  "address": "Dammam, Saudi Arabia",
  "phone": "+966 ...",
  "website": "https://example.com",
  "google_maps_url": "https://maps.google.com/...",
  "rating": 4.7,
  "review_count": 124,
  "types": ["medical_clinic"],
  "source_queries": ["medical clinic in Dammam"],
  "website_title": "Example Clinic",
  "website_description": "..."
}
```

## Verification

```bash
pytest -q
```

The tests use fake HTTP responses, so they do not require an API key or make
network requests.

## Notes

The Google Places API response and permitted uses remain subject to Google Maps
Platform policies. The project deliberately requests only the fields it needs.
