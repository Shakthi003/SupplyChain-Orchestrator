"""
retrieval/validator.py -- Document Upload Validator

Three-layer validation for user-uploaded documents before they are embedded.

Layer 1 — Text extraction check (always runs, free):
    Can we get text from the file at all? Is it long enough to be useful?

Layer 2 — Keyword relevance check (always runs, free, deterministic):
    Does the text contain keywords expected for the declared category?
    e.g. a "contract" should mention "supplier", "penalty", "delivery", etc.

Layer 3 — Gemini content check (runs if Layers 1+2 pass, 1 free-tier API call):
    Ask Gemini: "Is this a supply chain document?"
    Uses the exact same Gemini client already used in agents/nodes.py.
    Falls back gracefully if Gemini is unavailable (503 / rate limit).

Returns a ValidationResult with:
    - passed:   bool — True if document should be accepted
    - warnings: list of non-fatal messages to show the user
    - errors:   list of fatal messages (document rejected)
    - gemini_verdict: the raw Gemini response (or None)
"""

import time
from dataclasses import dataclass, field

from retrieval.parser import is_long_enough, MIN_CONTENT_LENGTH


# ---------------------------------------------------------------------------
# LAYER 2 — expected keywords per category
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "contract": [
        "supplier", "penalty", "delivery", "payment", "clause",
        "agreement", "contract", "terms", "liability", "obligation",
    ],
    "policy": [
        "policy", "approval", "threshold", "procedure", "escalate",
        "guideline", "authority", "process", "compliance", "rule",
    ],
    "past_decision": [
        "decision", "resolved", "delay", "approved", "rejected",
        "outcome", "action", "review", "case", "incident",
    ],
    "runbook": [
        "step", "action", "escalate", "notify", "checklist",
        "procedure", "respond", "contact", "resolution", "trigger",
    ],
    "other": [],  # no keyword check for "other"
}

# How many keywords must match to pass Layer 2
MIN_KEYWORD_MATCHES = 2

# How many characters to send to Gemini for Layer 3 (keep it short and cheap)
GEMINI_CONTEXT_CHARS = 800


# ---------------------------------------------------------------------------
# RESULT DATA CLASS
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    gemini_verdict: str | None = None

    def reject(self, message: str):
        self.passed = False
        self.errors.append(message)

    def warn(self, message: str):
        self.warnings.append(message)


# ---------------------------------------------------------------------------
# LAYER 1 — text length check
# ---------------------------------------------------------------------------

def _layer1_length(text: str, result: ValidationResult):
    if not is_long_enough(text):
        result.reject(
            f"Document has too little content ({len(text.strip())} characters). "
            f"Minimum required is {MIN_CONTENT_LENGTH} characters. "
            "Check that the file is not empty or a scanned image."
        )


# ---------------------------------------------------------------------------
# LAYER 2 — keyword relevance check
# ---------------------------------------------------------------------------

def _layer2_keywords(text: str, category: str, result: ValidationResult):
    keywords = CATEGORY_KEYWORDS.get(category, [])
    if not keywords:
        return  # "other" category — skip

    text_lower = text.lower()
    matched = [kw for kw in keywords if kw in text_lower]

    if len(matched) < MIN_KEYWORD_MATCHES:
        result.warn(
            f"This document doesn't look like a '{category}' — "
            f"only {len(matched)} of the expected keywords were found "
            f"({', '.join(matched) if matched else 'none'}). "
            f"Expected at least {MIN_KEYWORD_MATCHES} of: {', '.join(keywords[:6])}. "
            "You can still proceed if you're sure about the category."
        )


# ---------------------------------------------------------------------------
# LAYER 3 — Gemini content check
# ---------------------------------------------------------------------------

def _layer3_gemini(text: str, category: str, result: ValidationResult):
    """
    Ask Gemini whether this document is supply-chain relevant.
    Reuses the same genai client + retry pattern from agents/nodes.py.
    Falls back silently if Gemini is unavailable.
    """
    try:
        from google import genai
        from core.config import GEMINI_API_KEY, GEMINI_MODEL
    except ImportError:
        result.warn("Gemini content check skipped (google-genai not installed).")
        return

    if not GEMINI_API_KEY:
        result.warn("Gemini content check skipped (GEMINI_API_KEY not set).")
        return

    snippet = text.strip()[:GEMINI_CONTEXT_CHARS]
    prompt = (
        f"You are reviewing a document that a user wants to add to a supply chain "
        f"management system as category '{category}'.\n\n"
        f"Document excerpt:\n---\n{snippet}\n---\n\n"
        "Answer the following two questions in exactly this format:\n"
        "RELEVANT: YES or NO\n"
        "REASON: one sentence explanation\n\n"
        "RELEVANT means: does this document contain supply chain information such as "
        "supplier terms, delivery conditions, procurement policies, logistics procedures, "
        "past supply chain decisions, or disruption runbooks?"
    )

    # Use a background thread with a hard wall-clock timeout.
    # The Gemini free-tier client does not accept custom HttpOptions timeouts
    # (raises 400 INVALID_ARGUMENT). Threading is the only reliable way to
    # enforce a deadline without touching the SDK's internal config.
    import threading

    verdict_box: list[str] = []
    error_box:   list[str] = []

    def _call():
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            verdict_box.append(response.text.strip())
        except Exception as exc:
            error_box.append(str(exc))

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout=12)  # 12 s wall-clock — give up after this

    if thread.is_alive() or error_box:
        detail = error_box[0][:100] if error_box else "request timed out"
        result.warn(
            f"AI content check could not run (Gemini temporarily unavailable: {detail}). "
            "Your document passed the text and keyword checks and has been indexed successfully. "
            "The AI check only adds an extra relevance signal; it never blocks a valid upload."
        )
        return

    verdict = verdict_box[0] if verdict_box else ""
    result.gemini_verdict = verdict

    if "RELEVANT: NO" in verdict.upper():
        reason = ""
        for line in verdict.splitlines():
            if line.upper().startswith("REASON:"):
                reason = line.split(":", 1)[-1].strip()
                break
        result.warn(
            f"AI content check: this document may not be supply chain related. "
            f"Reason: {reason or verdict[:120]}. "
            "You can still proceed if you believe it belongs here."
        )
    # If RELEVANT: YES — no action needed, all good


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

def validate_document(
    text: str,
    category: str,
    run_gemini: bool = True,
) -> ValidationResult:
    """
    Run all three validation layers on extracted document text.

    Args:
        text:        Plain text extracted from the uploaded file
        category:    Declared category ("contract", "policy", etc.)
        run_gemini:  If False, skip Layer 3 (useful for tests)

    Returns:
        ValidationResult with passed, errors, warnings, gemini_verdict
    """
    result = ValidationResult()

    # Layer 1 — must pass to continue
    _layer1_length(text, result)
    if not result.passed:
        return result

    # Layer 2 — warnings only, never blocks
    _layer2_keywords(text, category, result)

    # Layer 3 — warnings only, never blocks, falls back gracefully
    if run_gemini:
        _layer3_gemini(text, category, result)

    return result
