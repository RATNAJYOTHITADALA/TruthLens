"""TruthLens Flask application, internal JSON API, and server-rendered pages."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, redirect, render_template, request, url_for

from db import (
    close_db,
    get_claim,
    get_summary,
    init_db,
    insert_claim,
    list_claims,
    update_claim_review,
)
from risk import assess_risk


PLATFORMS = ("WhatsApp", "X", "Instagram", "Other")
CATEGORIES = ("Politics", "Health", "Finance", "Other")
STATUSES = ("unverified", "verified_true", "verified_false", "misleading")
REVIEW_STATUSES = ("verified_true", "verified_false", "misleading")
STATUS_LABELS = {
    "unverified": "UNVERIFIED",
    "verified_true": "VERIFIED TRUE",
    "verified_false": "VERIFIED FALSE",
    "misleading": "MISLEADING",
}
RISK_LABELS = {
    "sensational": "SENSATIONAL",
    "shouting": "SHOUTING",
    "unsourced": "UNSOURCED",
}


def is_valid_http_url(value: str) -> bool:
    """Return whether value is an absolute HTTP or HTTPS URL with a host."""
    if not value or any(character.isspace() for character in value):
        return False

    try:
        parsed = urlsplit(value)
        # Accessing .port also validates that a supplied port is numeric and in range.
        _ = parsed.port
    except ValueError:
        return False

    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.hostname)


def validate_claim_payload(payload: dict) -> tuple[dict | None, dict[str, str]]:
    """Validate public claim input without accepting client-supplied risk data."""
    errors: dict[str, str] = {}
    claim_text = payload.get("claim_text")
    source_platform = payload.get("source_platform")
    category = payload.get("category")
    source_url = payload.get("source_url")

    if not isinstance(claim_text, str) or not claim_text.strip():
        errors["claim_text"] = "Claim text is required."
    if not isinstance(source_platform, str) or source_platform not in PLATFORMS:
        errors["source_platform"] = "Choose a supported source platform."
    if not isinstance(category, str) or category not in CATEGORIES:
        errors["category"] = "Choose a supported category."

    if source_url is not None:
        if not isinstance(source_url, str):
            errors["source_url"] = "Source URL must be a string."
        else:
            source_url = source_url.strip() or None
            if source_url is not None and not is_valid_http_url(source_url):
                errors["source_url"] = "Source URL must be a valid HTTP or HTTPS URL."

    if errors:
        return None, errors

    return {
        "claim_text": claim_text,
        "source_platform": source_platform,
        "source_url": source_url,
        "category": category,
    }, {}


def create_claim(payload: dict) -> tuple[dict | None, dict[str, str]]:
    """Validate, calculate risk on the server, and persist one claim."""
    claim_data, errors = validate_claim_payload(payload)
    if errors or claim_data is None:
        return None, errors

    risk = assess_risk(claim_data["claim_text"], claim_data["source_url"])
    claim = insert_claim(**claim_data, risk_flags=risk["risk_flags"], risk_score=risk["risk_score"])
    return claim, {}


def format_submitted_at(value: str) -> str:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).strftime("%b %d, %Y · %H:%M UTC")
    except (TypeError, ValueError):
        return value


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    default_database = Path(app.instance_path) / "truthlens.sqlite3"
    app.config.from_mapping(
        DATABASE=os.environ.get("TRUTHLENS_DATABASE", str(default_database)),
    )
    if test_config:
        app.config.from_mapping(test_config)

    init_db(app.config["DATABASE"])
    app.teardown_appcontext(close_db)
    app.add_template_filter(format_submitted_at, "submitted_at")

    @app.context_processor
    def template_labels():
        return {
            "status_labels": STATUS_LABELS,
            "risk_labels": RISK_LABELS,
        }

    @app.post("/api/claims")
    def create_claim_endpoint():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Expected a JSON object."), 400
        claim, errors = create_claim(payload)
        if errors or claim is None:
            return jsonify(error="Invalid claim.", details=errors), 400
        return jsonify(claim), 201

    @app.get("/api/claims")
    def list_claims_endpoint():
        category = request.args.get("category")
        status = request.args.get("status")
        errors: dict[str, str] = {}

        if category is not None and category not in CATEGORIES:
            errors["category"] = "Choose a supported category."
        if status is not None and status not in STATUSES:
            errors["status"] = "Choose a supported status."
        if errors:
            return jsonify(error="Invalid filter.", details=errors), 400

        claims = list_claims(category=category, status=status)
        return jsonify(claims=claims, count=len(claims))

    @app.get("/api/claims/<int:claim_id>")
    def get_claim_endpoint(claim_id: int):
        claim = get_claim(claim_id)
        if claim is None:
            return jsonify(error="Claim not found."), 404
        return jsonify(claim)

    @app.patch("/api/claims/<int:claim_id>")
    def review_claim_endpoint(claim_id: int):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Expected a JSON object."), 400

        claim = get_claim(claim_id)
        if claim is None:
            return jsonify(error="Claim not found."), 404

        unknown_fields = sorted(set(payload) - {"status", "reviewer_note"})
        if unknown_fields:
            return jsonify(
                error="Only status and reviewer_note can be changed.",
                details={field: "This field cannot be changed during review." for field in unknown_fields},
            ), 400

        status = payload.get("status")
        errors: dict[str, str] = {}
        if not isinstance(status, str) or status not in STATUSES:
            errors["status"] = "Choose a supported review status."

        update_note = "reviewer_note" in payload
        reviewer_note = payload.get("reviewer_note")
        if update_note:
            if reviewer_note is not None and not isinstance(reviewer_note, str):
                errors["reviewer_note"] = "Reviewer note must be text."
            elif isinstance(reviewer_note, str):
                reviewer_note = reviewer_note.strip() or None

        if errors:
            return jsonify(error="Invalid review.", details=errors), 400

        updated = update_claim_review(
            claim_id,
            status=status,
            reviewer_note=reviewer_note,
            update_note=update_note,
        )
        if updated is None:
            return jsonify(error="Claim not found."), 404
        return jsonify(updated)

    @app.get("/")
    def public_feed_page():
        selected_category = request.args.get("category", "")
        selected_status = request.args.get("status", "")
        if selected_category and selected_category not in CATEGORIES:
            return render_template(
                "error.html",
                title="Filter not recognized",
                message="Choose one of the listed categories and try again.",
                status_code=400,
            ), 400
        if selected_status and selected_status not in STATUSES:
            return render_template(
                "error.html",
                title="Filter not recognized",
                message="Choose one of the listed statuses and try again.",
                status_code=400,
            ), 400

        claims = list_claims(
            category=selected_category or None,
            status=selected_status or None,
        )
        return render_template(
            "feed.html",
            claims=claims,
            summary=get_summary(),
            categories=CATEGORIES,
            statuses=STATUSES,
            selected_category=selected_category,
            selected_status=selected_status,
            has_filters=bool(selected_category or selected_status),
        )

    @app.get("/submit")
    def submit_page():
        return render_template(
            "submit.html",
            platforms=PLATFORMS,
            categories=CATEGORIES,
            errors={},
            form_values={},
        )

    @app.post("/submit")
    def submit_claim_page():
        form_values = request.form.to_dict()
        claim, errors = create_claim(form_values)
        if errors or claim is None:
            return render_template(
                "submit.html",
                platforms=PLATFORMS,
                categories=CATEGORIES,
                errors=errors,
                form_values=form_values,
            ), 400
        return redirect(url_for("claim_detail_page", claim_id=claim["id"], submitted=1))

    @app.get("/claims/<int:claim_id>")
    def claim_detail_page(claim_id: int):
        claim = get_claim(claim_id)
        if claim is None:
            return render_template(
                "error.html",
                title="Claim not found",
                message="That claim may have been removed or the link may be incorrect.",
                status_code=404,
            ), 404
        return render_template(
            "detail.html",
            claim=claim,
            just_submitted=request.args.get("submitted") == "1",
        )

    @app.get("/review")
    def review_queue_page():
        return render_template(
            "review.html",
            claims=list_claims(status="unverified"),
            review_statuses=REVIEW_STATUSES,
        )

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found."), 404
        return render_template(
            "error.html",
            title="Page not found",
            message="The page you requested could not be found.",
            status_code=404,
        ), 404

    @app.errorhandler(500)
    def server_error(_error):
        if request.path.startswith("/api/"):
            return jsonify(error="The server could not complete that request. Please try again."), 500
        return render_template(
            "error.html",
            title="Something went wrong",
            message="TruthLens could not complete that request. Please try again.",
            status_code=500,
        ), 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run()
