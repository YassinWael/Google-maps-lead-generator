"""Normalize, enrich, deduplicate, and export lead records."""

import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


EXPORT_FIELDS = [
    "place_id",
    "name",
    "address",
    "phone",
    "website",
    "google_maps_url",
    "rating",
    "review_count",
    "types",
    "source_queries",
    "website_title",
    "website_description",
]


def normalize_place(raw: dict, query: str) -> dict:
    display_name = raw.get("displayName") or {}
    return {
        "place_id": raw.get("id", ""),
        "name": display_name.get("text", "").strip(),
        "address": raw.get("formattedAddress", ""),
        "phone": raw.get("internationalPhoneNumber", ""),
        "website": raw.get("websiteUri", ""),
        "google_maps_url": raw.get("googleMapsUri", ""),
        "rating": raw.get("rating"),
        "review_count": raw.get("userRatingCount", 0),
        "types": raw.get("types", []),
        "source_queries": [query],
        "website_title": "",
        "website_description": "",
    }


def collect_leads(
    client,
    queries: list[str],
    *,
    page_size: int = 20,
    max_pages: int = 1,
    min_rating: float = 0,
    min_reviews: int = 0,
) -> list[dict]:
    """Collect matching places and merge duplicates found by multiple queries."""
    leads_by_key: dict[str, dict] = {}

    for query in queries:
        for raw in client.search(query, page_size=page_size, max_pages=max_pages):
            lead = normalize_place(raw, query)
            if not lead["name"]:
                continue
            if (lead["rating"] or 0) < min_rating:
                continue
            if lead["review_count"] < min_reviews:
                continue

            key = lead["place_id"] or f'{lead["name"].lower()}|{lead["address"].lower()}'
            existing = leads_by_key.get(key)
            if existing:
                if query not in existing["source_queries"]:
                    existing["source_queries"].append(query)
            else:
                leads_by_key[key] = lead

    return sorted(
        leads_by_key.values(),
        key=lambda lead: (-(lead["rating"] or 0), -lead["review_count"], lead["name"]),
    )


def fetch_website_metadata(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = 12,
) -> dict:
    """Return a page title and description without failing the wider pipeline."""
    if urlparse(url).scheme not in {"http", "https"}:
        return {}

    try:
        response = (session or requests).get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; lead-pipeline/1.0)"},
            timeout=timeout,
        )
        response.raise_for_status()
        if "html" not in response.headers.get("Content-Type", "").lower():
            return {}
    except requests.RequestException:
        return {}

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    description_tag = soup.find("meta", attrs={"name": "description"})
    description = description_tag.get("content", "").strip() if description_tag else ""
    return {
        "website_title": title[:200],
        "website_description": description[:500],
    }


def enrich_websites(leads: list[dict], *, workers: int = 6, fetcher=fetch_website_metadata) -> None:
    """Add website metadata concurrently while preserving lead order."""
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(fetcher, lead["website"]): lead
            for lead in leads
            if lead.get("website")
        }
        for future in as_completed(futures):
            lead = futures[future]
            try:
                lead.update(future.result())
            except Exception:
                continue


def write_exports(leads: list[dict], output_dir: str | Path) -> tuple[Path, Path]:
    """Write deterministic JSON and CSV files and return their paths."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "leads.json"
    csv_path = output_path / "leads.csv"

    json_path.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=EXPORT_FIELDS)
        writer.writeheader()
        for lead in leads:
            row = dict(lead)
            row["types"] = ",".join(row["types"])
            row["source_queries"] = " | ".join(row["source_queries"])
            writer.writerow(row)

    return json_path, csv_path
