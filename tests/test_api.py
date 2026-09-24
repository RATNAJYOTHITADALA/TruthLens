import sqlite3

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "truthlens-test.sqlite3"),
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


def valid_payload(**overrides):
    payload = {
        "claim_text": "A local school will close tomorrow.",
        "source_platform": "WhatsApp",
        "category": "Other",
    }
    payload.update(overrides)
    return payload


def test_create_claim_defaults_to_unverified_and_calculates_risk_on_server(client):
    response = client.post(
        "/api/claims",
        json=valid_payload(
            claim_text="BREAKING SHOCKING update",
            risk_flags=[],
            risk_score=0,
            high_risk=False,
            status="Verified True",
        ),
    )

    assert response.status_code == 201
    claim = response.get_json()
    assert claim["status"] == "unverified"
    assert claim["risk_flags"] == ["sensational", "shouting", "unsourced"]
    assert claim["risk_score"] == 3
    assert claim["high_risk"] is True


def test_create_claim_accepts_a_valid_source_url(client):
    response = client.post(
        "/api/claims",
        json=valid_payload(source_url="https://example.com/story"),
    )
    assert response.status_code == 201
    assert response.get_json()["source_url"] == "https://example.com/story"
    assert "unsourced" not in response.get_json()["risk_flags"]


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"claim_text": "   "}, "claim_text"),
        ({"source_platform": "TikTok"}, "source_platform"),
        ({"category": "Science"}, "category"),
        ({"source_url": "javascript:alert(1)"}, "source_url"),
        ({"source_url": "https://bad host/path"}, "source_url"),
    ],
)
def test_create_rejects_invalid_input(client, overrides, field):
    response = client.post("/api/claims", json=valid_payload(**overrides))
    assert response.status_code == 400
    assert field in response.get_json()["details"]


def test_create_rejects_a_non_json_body(client):
    response = client.post("/api/claims", data="claim text")
    assert response.status_code == 400


def test_list_and_detail_return_created_claim(client):
    created = client.post("/api/claims", json=valid_payload()).get_json()

    listed = client.get("/api/claims").get_json()
    detailed = client.get(f"/api/claims/{created['id']}")

    assert listed["count"] == 1
    assert listed["claims"][0]["id"] == created["id"]
    assert detailed.status_code == 200
    assert detailed.get_json()["claim_text"] == "A local school will close tomorrow."
    assert detailed.get_json()["created_at"].endswith("Z")


def test_category_status_and_combined_filters(client):
    politics = client.post(
        "/api/claims",
        json=valid_payload(category="Politics", claim_text="Political claim."),
    ).get_json()
    health = client.post(
        "/api/claims",
        json=valid_payload(category="Health", claim_text="Health claim."),
    ).get_json()
    with sqlite3.connect(client.application.config["DATABASE"]) as connection:
        connection.execute(
            "UPDATE claims SET status = 'verified_false' WHERE id = ?", (politics["id"],)
        )

    assert client.get("/api/claims?category=Health").get_json()["count"] == 1
    assert client.get("/api/claims?status=unverified").get_json()["count"] == 1
    combined = client.get(
        "/api/claims?category=Politics&status=verified_false"
    ).get_json()
    assert [claim["id"] for claim in combined["claims"]] == [politics["id"]]
    assert health["id"] != politics["id"]


def test_list_uses_all_four_risk_priority_groups_and_newest_first_within_group(client, app):
    high_unverified_old = client.post(
        "/api/claims", json=valid_payload(claim_text="BREAKING SHOCKING report")
    ).get_json()
    high_unverified_new = client.post(
        "/api/claims", json=valid_payload(claim_text="BREAKING SHOCKING update")
    ).get_json()
    high_reviewed = client.post(
        "/api/claims", json=valid_payload(claim_text="BREAKING report")
    ).get_json()
    unverified = client.post(
        "/api/claims", json=valid_payload(claim_text="A normal unsourced report")
    ).get_json()
    reviewed = client.post(
        "/api/claims",
        json=valid_payload(
            claim_text="A sourced report", source_url="https://example.com/report"
        ),
    ).get_json()

    timestamps = {
        high_unverified_old["id"]: "2026-01-01T00:00:00.000000Z",
        high_unverified_new["id"]: "2026-01-02T00:00:00.000000Z",
        high_reviewed["id"]: "2026-01-05T00:00:00.000000Z",
        unverified["id"]: "2026-01-04T00:00:00.000000Z",
        reviewed["id"]: "2026-01-06T00:00:00.000000Z",
    }
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        for claim_id, created_at in timestamps.items():
            connection.execute(
                "UPDATE claims SET created_at = ? WHERE id = ?", (created_at, claim_id)
            )
        connection.execute(
            "UPDATE claims SET status = 'verified_true' WHERE id = ?", (high_reviewed["id"],)
        )
        connection.execute(
            "UPDATE claims SET status = 'misleading' WHERE id = ?", (reviewed["id"],)
        )

    ordered = client.get("/api/claims").get_json()["claims"]
    assert [claim["id"] for claim in ordered] == [
        high_unverified_new["id"],
        high_unverified_old["id"],
        high_reviewed["id"],
        unverified["id"],
        reviewed["id"],
    ]


def test_unknown_claim_id_returns_404(client):
    response = client.get("/api/claims/9999")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Claim not found."


def test_patch_review_updates_status_and_trims_reviewer_note(client):
    created = client.post("/api/claims", json=valid_payload()).get_json()

    response = client.patch(
        f"/api/claims/{created['id']}",
        json={"status": "verified_true", "reviewer_note": "  Source checked.  \n"},
    )

    assert response.status_code == 200
    updated = response.get_json()
    assert updated["status"] == "verified_true"
    assert updated["reviewer_note"] == "Source checked."
    assert updated["claim_text"] == created["claim_text"]


def test_patch_review_allows_note_to_be_omitted_and_preserves_existing_note(client):
    created = client.post("/api/claims", json=valid_payload()).get_json()
    client.patch(
        f"/api/claims/{created['id']}",
        json={"status": "verified_true", "reviewer_note": "Evidence reviewed."},
    )

    response = client.patch(
        f"/api/claims/{created['id']}",
        json={"status": "verified_false"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "verified_false"
    assert response.get_json()["reviewer_note"] == "Evidence reviewed."


def test_patch_review_rejects_invalid_status(client):
    created = client.post("/api/claims", json=valid_payload()).get_json()

    response = client.patch(
        f"/api/claims/{created['id']}",
        json={"status": "confirmed"},
    )

    assert response.status_code == 400
    assert "status" in response.get_json()["details"]


def test_patch_review_rejects_claim_text_and_keeps_original_unchanged(client):
    created = client.post("/api/claims", json=valid_payload()).get_json()

    response = client.patch(
        f"/api/claims/{created['id']}",
        json={
            "status": "verified_true",
            "reviewer_note": "Context belongs in the note.",
            "claim_text": "A replacement claim.",
        },
    )

    assert response.status_code == 400
    assert "claim_text" in response.get_json()["details"]
    stored = client.get(f"/api/claims/{created['id']}").get_json()
    assert stored["claim_text"] == "A local school will close tomorrow."
    assert stored["status"] == "unverified"
    assert stored["reviewer_note"] is None


def test_patch_review_rejects_unknown_claim_id(client):
    response = client.patch("/api/claims/9999", json={"status": "misleading"})
    assert response.status_code == 404


def test_patch_review_rejects_non_text_note(client):
    created = client.post("/api/claims", json=valid_payload()).get_json()
    response = client.patch(
        f"/api/claims/{created['id']}",
        json={"status": "misleading", "reviewer_note": 42},
    )
    assert response.status_code == 400
    assert "reviewer_note" in response.get_json()["details"]


def test_app_migrates_existing_title_case_statuses_without_losing_claim_data(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """CREATE TABLE claims (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   claim_text TEXT NOT NULL CHECK (length(trim(claim_text)) > 0),
                   source_platform TEXT NOT NULL CHECK (source_platform IN ('WhatsApp', 'X', 'Instagram', 'Other')),
                   source_url TEXT,
                   category TEXT NOT NULL CHECK (category IN ('Politics', 'Health', 'Finance', 'Other')),
                   risk_flags TEXT NOT NULL,
                   risk_score INTEGER NOT NULL CHECK (risk_score BETWEEN 0 AND 3),
                   status TEXT NOT NULL DEFAULT 'Unverified'
                       CHECK (status IN ('Unverified', 'Verified True', 'Verified False', 'Misleading')),
                   reviewer_note TEXT,
                   created_at TEXT NOT NULL
               );
               CREATE INDEX idx_claims_created_at ON claims(created_at DESC);
               INSERT INTO claims
                   (claim_text, source_platform, source_url, category, risk_flags,
                    risk_score, status, reviewer_note, created_at)
               VALUES
                   ('Original stored wording', 'X', 'https://example.com', 'Politics',
                    '["sensational"]', 1, 'Verified False', 'Legacy note', '2026-01-01T00:00:00Z');"""
        )

    app = create_app({"TESTING": True, "DATABASE": str(database)})
    claim = app.test_client().get("/api/claims/1").get_json()

    assert claim["status"] == "verified_false"
    assert claim["claim_text"] == "Original stored wording"
    assert claim["reviewer_note"] == "Legacy note"
