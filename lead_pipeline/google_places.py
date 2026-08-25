"""Minimal client for the Google Places Text Search API."""

from collections.abc import Iterator
from time import sleep

import requests


class PlacesAPIError(RuntimeError):
    """Raised when Google Places cannot return a valid response."""


class GooglePlacesClient:
    endpoint = "https://places.googleapis.com/v1/places:searchText"
    field_mask = ",".join(
        [
            "places.id",
            "places.displayName",
            "places.formattedAddress",
            "places.internationalPhoneNumber",
            "places.websiteUri",
            "places.googleMapsUri",
            "places.rating",
            "places.userRatingCount",
            "places.types",
            "nextPageToken",
        ]
    )

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        timeout: int = 20,
        max_retries: int = 3,
        sleep_fn=sleep,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_retries = max_retries
        self.sleep = sleep_fn
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": self.field_mask,
        }

    def search(
        self,
        query: str,
        *,
        page_size: int = 20,
        max_pages: int = 1,
    ) -> Iterator[dict]:
        """Yield raw place records across one or more result pages."""
        query = query.strip()
        if not query:
            raise ValueError("query cannot be empty")
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")

        body = {
            "textQuery": query,
            "pageSize": min(max(page_size, 1), 20),
        }
        page_token = None

        for _ in range(max_pages):
            if page_token:
                body["pageToken"] = page_token

            data = self._post(body)
            yield from data.get("places", [])

            page_token = data.get("nextPageToken")
            if not page_token:
                break

    def _post(self, body: dict) -> dict:
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    self.endpoint,
                    headers=self.headers,
                    json=body,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("response JSON must be an object")
                return data
            except (requests.RequestException, ValueError) as error:
                last_error = error
                if attempt + 1 < self.max_retries:
                    self.sleep(2**attempt)

        raise PlacesAPIError("Google Places request failed after retries") from last_error
