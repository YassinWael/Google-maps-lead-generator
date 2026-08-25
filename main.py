"""Command-line entry point for the lead pipeline."""

import argparse
import os

from dotenv import load_dotenv

from lead_pipeline import GooglePlacesClient, collect_leads, enrich_websites, write_exports


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect normalized leads from Google Places")
    parser.add_argument("--query", action="append", required=True, help="Search query; repeat as needed")
    parser.add_argument("--pages", type=int, default=1, help="Pages per query, from 1 to 3")
    parser.add_argument("--page-size", type=int, default=20, help="Results per page, from 1 to 20")
    parser.add_argument("--min-rating", type=float, default=0)
    parser.add_argument("--min-reviews", type=int, default=0)
    parser.add_argument("--enrich-websites", action="store_true")
    parser.add_argument("--output-dir", default="output")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise SystemExit("Set GOOGLE_MAPS_API_KEY in the environment or .env file")

    client = GooglePlacesClient(api_key)
    leads = collect_leads(
        client,
        args.query,
        page_size=args.page_size,
        max_pages=min(max(args.pages, 1), 3),
        min_rating=args.min_rating,
        min_reviews=args.min_reviews,
    )
    if args.enrich_websites:
        enrich_websites(leads)

    json_path, csv_path = write_exports(leads, args.output_dir)
    print(f"Collected {len(leads)} unique leads")
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")


if __name__ == "__main__":
    main()
