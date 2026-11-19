"""Explicit download helper for the optional Stanza Spanish pilot models."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download only the Spanish Stanza processors used by the NLP pilot."
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path.home() / "stanza_resources",
        help="Local Stanza resource directory (download is explicit, never at app startup).",
    )
    args = parser.parse_args()

    try:
        import stanza
    except ImportError:
        parser.error(
            "Stanza is optional. Install it first with: pip install --group nlp-pilot"
        )

    model_dir = args.model_dir.expanduser().resolve()
    model_dir.mkdir(parents=True, exist_ok=True)
    stanza.download(
        lang="es",
        processors="tokenize,mwt,pos,lemma,depparse",
        model_dir=str(model_dir),
        verbose=False,
    )
    print(f"Stanza Spanish pilot models installed in: {model_dir}")
    print("Processors: tokenize,mwt,pos,lemma,depparse")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
