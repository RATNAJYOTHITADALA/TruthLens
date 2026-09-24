import sqlite3

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "truthlens-pages-test.sqlite3"),
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


def submit_claim(client, claim_text, *, category="Other", source_url=None):
    payload = {
        "claim_text": claim_text,
        "source_platform": "WhatsApp",
        "category": category,
    }
    if source_url is not None:
        payload["source_url"] = source_url
    response = client.post("/api/claims", json=payload)
    assert response.status_code == 201
    return response.get_json()


def test_public_feed_shows_database_summary_and_unverified_claim(client):
    submit_claim(client, "A local clinic will close tomorrow.", category="Health")
    submit_claim(client, "BREAKING SHOCKING report", category="Politics")

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Public claim desk" in html
    assert "TOTAL CLAIMS" in html and "2" in html
    assert "HIGH RISK" in html
    assert "UNVERIFIED" in html
    assert "This claim has not yet been reviewed." in html
    assert "A local clinic will close tomorrow." in html
    assert "BREAKING SHOCKING report" in html
    assert "View details" in html


def test_public_feed_filters_by_category_and_status_together(client, app):
    health_unverified = submit_claim(client, "Health item one", category="Health")
    submit_claim(client, "Politics item", category="Politics")
    health_reviewed = submit_claim(client, "Health item two", category="Health")
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        connection.execute(
            "UPDATE claims SET status = 'verified_true' WHERE id = ?",
            (health_reviewed["id"],),
        )

    response = client.get("/?category=Health&status=unverified")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Health item one" in html
    assert "Politics item" not in html
    assert "Health item two" not in html
    assert health_unverified["id"] != health_reviewed["id"]


def test_public_feed_shows_no_claims_empty_state(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "No claims have been submitted yet." in response.get_data(as_text=True)


def test_public_feed_shows_filtered_empty_state(client):
    submit_claim(client, "A finance item", category="Finance")
    response = client.get("/?category=Health")
    assert response.status_code == 200
    assert "No claims match the selected filters." in response.get_data(as_text=True)


def test_public_feed_rejects_unknown_filter_with_friendly_page(client):
    response = client.get("/?status=confirmed")
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Filter not recognized" in html
    assert "Traceback" not in html


def test_submit_page_has_all_required_fields_and_options(client):
    response = client.get("/submit")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="claim_text"' in html
    assert 'name="source_platform"' in html
    assert 'name="category"' in html
    assert 'name="source_url"' in html
    assert "WhatsApp" in html and "Instagram" in html and ">X<" in html
    assert "Politics" in html and "Health" in html and "Finance" in html
    assert "Analyze &amp; Submit" in html
    assert "data-api-url=\"/api/claims\"" in html


def test_submit_page_fallback_validates_and_redirects_to_detail(client):
    invalid = client.post(
        "/submit",
        data={"claim_text": " ", "source_platform": "WhatsApp", "category": "Other"},
    )
    assert invalid.status_code == 400
    assert "Claim text is required." in invalid.get_data(as_text=True)

    response = client.post(
        "/submit",
        data={
            "claim_text": "An unsourced community claim.",
            "source_platform": "X",
            "category": "Other",
            "source_url": "",
        },
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Claim submitted. It is now visible in the public feed." in html
    assert "ORIGINAL SUBMITTED CLAIM" in html
    assert "An unsourced community claim." in html


def test_detail_page_shows_full_claim_source_flags_status_and_separate_note(client):
    claim = submit_claim(
        client,
        "BREAKING news from the community. This complete claim stays unchanged.",
        category="Politics",
        source_url="https://example.com/story",
    )
    client.patch(
        f"/api/claims/{claim['id']}",
        json={"status": "verified_false", "reviewer_note": "Reviewed source context."},
    )

    response = client.get(f"/claims/{claim['id']}")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "TRUTHLENS CLAIM DETAIL" in html
    assert "VERIFIED FALSE" in html
    assert "Politics" in html
    assert "WhatsApp" in html
    assert "https://example.com/story" in html
    assert "SENSATIONAL" in html
    assert "UNSOURCED" not in html
    assert "ORIGINAL SUBMITTED CLAIM" in html
    assert "BREAKING news from the community. This complete claim stays unchanged." in html
    assert "REVIEWER NOTE" in html
    assert "Reviewed source context." in html


def test_unverified_detail_has_warning_and_empty_note_state(client):
    claim = submit_claim(client, "A claim without a review note.")
    response = client.get(f"/claims/{claim['id']}")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "UNVERIFIED" in html
    assert "This claim has not yet been reviewed." in html
    assert "No reviewer note has been added." in html


def test_unknown_detail_page_is_friendly_and_does_not_expose_traceback(client):
    response = client.get("/claims/9999")
    html = response.get_data(as_text=True)
    assert response.status_code == 404
    assert "Claim not found" in html
    assert "Traceback" not in html


def test_review_page_shows_unverified_claims_in_risk_order_only(client, app):
    low_risk = submit_claim(client, "A regular unsourced item.")
    high_risk = submit_claim(client, "BREAKING SHOCKING community item.")
    reviewed = submit_claim(client, "A reviewed item.", source_url="https://example.com")
    client.patch(f"/api/claims/{reviewed['id']}", json={"status": "misleading"})

    response = client.get("/review")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.index("BREAKING SHOCKING community item.") < html.index("A regular unsourced item.")
    assert "A reviewed item." not in html
    assert "HIGH RISK" in html
    assert "Open claim" in html
    assert 'name="status"' in html
    assert 'name="reviewer_note"' in html
    assert "Save Review" in html
    assert "claim_text" not in html


def test_review_page_shows_empty_queue_message(client):
    reviewed = submit_claim(client, "Already reviewed item.")
    client.patch(f"/api/claims/{reviewed['id']}", json={"status": "verified_true"})
    response = client.get("/review")
    assert response.status_code == 200
    assert "No claims are waiting for review." in response.get_data(as_text=True)
