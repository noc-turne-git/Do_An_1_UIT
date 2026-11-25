"""Shared fallback and destination issuance rule; runtime values come from AISettings."""

DEFAULT_MAX_DESTINATION_ROUNDS = 10


def destination_question_allowed(kind: str, consumed: int, maximum: int) -> bool:
    """Both destination kinds consume a round; choices may continue past the cap.

    The cap ends information gathering, never the user's opportunity to choose,
    refine or delegate. Historical counters can therefore exceed a lowered cap.
    """
    return kind == 'destination_choice' or consumed < maximum
