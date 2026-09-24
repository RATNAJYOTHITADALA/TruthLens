# TruthLens Decision Points

## DP1 — Feed ordering

**Decision:** Prioritize claims using risk signals and review status, then show the newest submissions first within each priority group.

This ordering brings high-risk unverified claims to the top, followed by other high-risk claims and unverified claims, while still using submission time to order claims within each group. Reviewers can spot potentially higher-priority items sooner, and the explicit groups make the feed order understandable.

## DP2 — Visibility of unverified claims

**Decision:** Keep unverified claims publicly visible, label them **UNVERIFIED**, and visually distinguish them.

Hiding unverified submissions would reduce transparency about what has been reported and what still needs review. Showing them without a clear warning could lead readers to mistake an unchecked claim for a confirmed fact. The visible label helps readers interpret the claim while keeping it available to reviewers and the public.

## DP3 — Editing after submission

**Decision:** The original submitted claim text cannot be edited through the normal frontend or API review flow; reviewers can change only status and reviewer note.

Preserving the original wording creates an audit trail of what was submitted and prevents silent changes to the claim under review. Reviewers can add context through their note and record an outcome through the status. This lets readers and reviewers distinguish the original submission from later review information.
