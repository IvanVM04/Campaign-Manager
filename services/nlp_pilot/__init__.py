"""Optional, non-authoritative NLP experiments.

Nothing in the production turn pipeline imports this package. Importing it
never imports Stanza or downloads model files.
"""

from services.nlp_pilot.contracts import (
    ParserDocument,
    ParserSentence,
    ParserWord,
    render_prompt_hint_section,
)

__all__ = [
    "ParserDocument",
    "ParserSentence",
    "ParserWord",
    "render_prompt_hint_section",
]
