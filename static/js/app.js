"use strict";

function clearFieldErrors(form) {
  form.querySelectorAll("[data-field-error]").forEach((element) => {
    element.textContent = "";
  });
  form.querySelectorAll("[aria-invalid='true']").forEach((element) => {
    element.removeAttribute("aria-invalid");
  });
}

function showClaimFormErrors(form, details) {
  let hasFieldError = false;
  Object.entries(details || {}).forEach(([field, message]) => {
    const errorElement = Array.from(form.querySelectorAll("[data-field-error]"))
      .find((element) => element.dataset.fieldError === field);
    const input = form.elements.namedItem(field);
    if (errorElement) {
      errorElement.textContent = message;
      hasFieldError = true;
    }
    if (input && typeof input.setAttribute === "function") {
      input.setAttribute("aria-invalid", "true");
    }
  });
  return hasFieldError;
}

function setFeedback(element, message, isError = true) {
  if (!element) return;
  element.textContent = message;
  element.hidden = !message;
  element.classList.toggle("feedback-error", isError && Boolean(message));
}

const claimForm = document.querySelector("#claim-form");
if (claimForm) {
  claimForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearFieldErrors(claimForm);

    const feedback = claimForm.querySelector("[data-form-feedback]");
    const button = claimForm.querySelector("[data-submit-button]");
    const originalButtonText = button.textContent;
    const payload = Object.fromEntries(new FormData(claimForm).entries());

    setFeedback(feedback, "Submitting claim…", false);
    button.disabled = true;
    button.textContent = "Submitting…";
    claimForm.setAttribute("aria-busy", "true");

    try {
      const response = await fetch(claimForm.dataset.apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        showClaimFormErrors(claimForm, result.details);
        setFeedback(
          feedback,
          result.error || "The claim could not be submitted. Check the fields and try again.",
        );
        return;
      }
      window.location.assign(`/claims/${encodeURIComponent(result.id)}?submitted=1`);
    } catch (_error) {
      setFeedback(feedback, "Could not reach TruthLens. Check your connection and try again.");
    } finally {
      button.disabled = false;
      button.textContent = originalButtonText;
      claimForm.removeAttribute("aria-busy");
    }
  });
}

function appendReviewSuccess(claimId, status) {
  const region = document.querySelector("#review-success");
  if (!region) return;
  const labels = {
    unverified: "UNVERIFIED",
    verified_true: "VERIFIED TRUE",
    verified_false: "VERIFIED FALSE",
    misleading: "MISLEADING",
  };
  region.replaceChildren();
  const icon = document.createElement("span");
  icon.className = "notice-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = "✓";
  const message = document.createElement("p");
  message.textContent = `Review saved as ${labels[status] || status}.`;
  const links = document.createElement("span");
  links.className = "review-success-link";
  const detailLink = document.createElement("a");
  detailLink.href = `/claims/${encodeURIComponent(claimId)}`;
  detailLink.textContent = "View claim";
  const feedLink = document.createElement("a");
  feedLink.href = "/";
  feedLink.textContent = "Return to public feed";
  links.append(detailLink, feedLink);
  region.append(icon, message, links);
  region.hidden = false;
}

document.querySelectorAll("[data-review-form]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("[data-review-button]");
    const error = form.querySelector("[data-review-error]");
    const originalButtonText = button.textContent;
    const payload = Object.fromEntries(new FormData(form).entries());
    error.textContent = "";
    error.hidden = true;
    button.disabled = true;
    button.textContent = "Saving…";

    try {
      const response = await fetch(form.dataset.apiUrl, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        error.textContent = result.error || "The review could not be saved. Please try again.";
        if (result.details) {
          error.textContent += ` ${Object.values(result.details).join(" ")}`;
        }
        error.hidden = false;
        return;
      }

      appendReviewSuccess(result.id, result.status);
      const card = document.querySelector(`#review-card-${form.dataset.claimId}`);
      if (card) card.remove();
      const remaining = document.querySelectorAll("[data-review-form]").length;
      const emptyState = document.querySelector("#review-empty-state");
      if (remaining === 0 && emptyState) emptyState.hidden = false;
    } catch (_error) {
      error.textContent = "Could not reach TruthLens. Check your connection and try again.";
      error.hidden = false;
    } finally {
      button.disabled = false;
      button.textContent = originalButtonText;
    }
  });
});
