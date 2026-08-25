import json

import requests

from lead_pipeline.google_places import GooglePlacesClient, PlacesAPIError
from lead_pipeline.pipeline import collect_leads, fetch_website_metadata, write_exports


class FakeResponse:
    def __init__(self, data=None, *, status_code=200, text="", content_type="application/json"):
        self.data = data
        self.status_code = status_code
        self.text = text
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def place(place_id="one", name="Clinic", rating=4.8, reviews=20):
    return {
        "id": place_id,
        "displayName": {"text": name},
        "formattedAddress": "Dammam, Saudi Arabia",
        "internationalPhoneNumber": "+966 000 0000",
        "websiteUri": "https://example.com",
        "googleMapsUri": "https://maps.example.com/place",
        "rating": rating,
        "userRatingCount": reviews,
        "types": ["medical_clinic"],
    }


def test_client_follows_page_token():
    session = FakeSession(
        [
            FakeResponse({"places": [place("one")], "nextPageToken": "page-two"}),
            FakeResponse({"places": [place("two", "Second Clinic")]}),
        ]
    )
    client = GooglePlacesClient("test-key", session=session, sleep_fn=lambda _: None)

    results = list(client.search("clinic in Dammam", max_pages=2))

    assert [result["id"] for result in results] == ["one", "two"]
    assert session.calls[1][1]["json"]["pageToken"] == "page-two"
    assert session.calls[0][1]["headers"]["X-Goog-Api-Key"] == "test-key"


def test_client_retries_transient_failure():
    sleeps = []
    session = FakeSession([FakeResponse(status_code=429), FakeResponse({"places": []})])
    client = GooglePlacesClient("test-key", session=session, sleep_fn=sleeps.append)

    assert list(client.search("clinic")) == []
    assert sleeps == [1]


def test_client_raises_after_retry_limit():
    session = FakeSession([FakeResponse(status_code=500), FakeResponse(status_code=500)])
    client = GooglePlacesClient("test-key", session=session, max_retries=2, sleep_fn=lambda _: None)

    try:
        list(client.search("clinic"))
    except PlacesAPIError:
        pass
    else:
        raise AssertionError("PlacesAPIError was not raised")


def test_collect_leads_filters_and_merges_queries():
    class FakeClient:
        def search(self, query, **_):
            return [place("one", rating=4.7, reviews=30), place("low", rating=3.0, reviews=2)]

    leads = collect_leads(
        FakeClient(),
        ["clinic in Dammam", "medical business in Dammam"],
        min_rating=4,
        min_reviews=10,
    )

    assert len(leads) == 1
    assert leads[0]["place_id"] == "one"
    assert leads[0]["source_queries"] == [
        "clinic in Dammam",
        "medical business in Dammam",
    ]


def test_website_metadata_parses_html():
    html = """
    <html><head><title>Example Clinic</title>
    <meta name="description" content="Independent medical clinic"></head></html>
    """
    session = FakeSession([FakeResponse(text=html, content_type="text/html; charset=utf-8")])

    metadata = fetch_website_metadata("https://example.com", session=session)

    assert metadata == {
        "website_title": "Example Clinic",
        "website_description": "Independent medical clinic",
    }


def test_exports_are_readable(tmp_path):
    leads = [
        {
            "place_id": "one",
            "name": "Clinic",
            "address": "Dammam",
            "phone": "",
            "website": "",
            "google_maps_url": "",
            "rating": 4.8,
            "review_count": 20,
            "types": ["clinic"],
            "source_queries": ["clinic"],
            "website_title": "",
            "website_description": "",
        }
    ]

    json_path, csv_path = write_exports(leads, tmp_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))[0]["place_id"] == "one"
    assert "source_queries" in csv_path.read_text(encoding="utf-8")
