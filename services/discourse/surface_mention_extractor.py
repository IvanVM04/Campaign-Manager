"""Literal mention extraction and local grammatical-surface features."""

from __future__ import annotations

import re
from typing import ClassVar

from services.discourse.contracts import SurfacePronounMention
from services.discourse.text import DiscourseText


class SurfaceMentionExtractor(DiscourseText):
    """Extract source spans only; never infer a canonical referent."""

    _ARTICLES: ClassVar[dict[str, tuple[str, str]]] = {
        "el": ("masculine", "singular"), "un": ("masculine", "singular"),
        "este": ("masculine", "singular"), "aquel": ("masculine", "singular"),
        "la": ("feminine", "singular"), "una": ("feminine", "singular"),
        "esta": ("feminine", "singular"), "aquella": ("feminine", "singular"),
        "los": ("masculine", "plural"), "unos": ("masculine", "plural"),
        "estos": ("masculine", "plural"), "aquellos": ("masculine", "plural"),
        "las": ("feminine", "plural"), "unas": ("feminine", "plural"),
        "estas": ("feminine", "plural"), "aquellas": ("feminine", "plural"),
    }
    _PRONOUNS: ClassVar[dict[str, tuple[str, str]]] = {
        "el": ("masculine", "singular"), "él": ("masculine", "singular"),
        "lo": ("masculine", "singular"), "ese": ("masculine", "singular"),
        "este": ("masculine", "singular"), "aquel": ("masculine", "singular"),
        "ella": ("feminine", "singular"), "la": ("feminine", "singular"),
        "esa": ("feminine", "singular"), "esta": ("feminine", "singular"),
        "aquella": ("feminine", "singular"), "ellos": ("masculine", "plural"),
        "los": ("masculine", "plural"), "esos": ("masculine", "plural"),
        "estos": ("masculine", "plural"), "aquellos": ("masculine", "plural"),
        "ellas": ("feminine", "plural"), "las": ("feminine", "plural"),
        "esas": ("feminine", "plural"), "estas": ("feminine", "plural"),
        "aquellas": ("feminine", "plural"),
    }
    _HUMAN_HEADS = frozenset({
        "guardia", "guardias", "soldado", "soldados", "capitan", "capitana",
        "mercader", "mercadera", "mago", "maga", "hechicero", "hechicera",
        "clerigo", "cleriga", "sacerdote", "sacerdotisa", "arquero", "arquera",
        "ladron", "ladrona", "tabernero", "tabernera", "posadero", "posadera",
        "cartografo", "cartografa", "viajero", "viajera", "anciano", "anciana",
        "hombre", "mujer", "chico", "chica", "rey", "reina", "principe",
        "princesa", "duque", "duquesa", "noble", "sirviente", "sirvienta",
        "explorador", "exploradora", "guerrero", "guerrera", "curandero",
        "curandera", "artesano", "artesana",
    })
    @classmethod
    def surface_pronoun_mentions(cls, value: str) -> tuple[SurfacePronounMention, ...]:
        """Extract literal subject pronouns and narrowly recognized dative clitics."""
        if not isinstance(value, str) or not value:
            return ()
        masked = cls._mask_quoted_spans(value)
        subject_pattern = re.compile(
            r"(?<!\w)(?P<pronoun>ellas|ellos|ella|él|she|he|they)(?!\w)",
            re.IGNORECASE,
        )
        # "le" is also a feminine article and "les" has other uses. Treat
        # them as clitics only when immediately followed by a known finite
        # verb form; never classify "la puerta" as an object reference.
        clitic_verbs = (
            "pregunto|pregunta|pregunté|preguntó|preguntan|preguntaba|preguntaron|"
            "digo|dice|dijo|dije|dicen|decía|"
            "respondo|responde|respondió|respondí|responden|"
            "contesto|contesta|contestó|contesté|contestan|"
            "entrego|entrega|entregó|entregué|entregan|"
            "ofrezco|ofrece|ofreció|ofrecí|pido|pide|pidió|pedí|"
            "aviso|avisa|avisó|avisé|muestro|muestra|mostró|mostré|"
            "doy|da|dio|di|llamo|llama|llamó|llamé|"
            "saludo|saluda|saludó|saludé|explico|explica|explicó|expliqué|"
            "cuento|cuenta|contó|conté|escribo|escribe|escribió|escribí"
        )
        clitic_pattern = re.compile(
            r"(?<!\w)(?P<pronoun>les|le)\s+"
            r"(?P<verb>" + clitic_verbs + r")(?!\w)",
            re.IGNORECASE,
        )
        found: list[SurfacePronounMention] = []
        seen_spans: set[tuple[int, int]] = set()
        for pattern in (subject_pattern, clitic_pattern):
            for match in pattern.finditer(masked):
                start = match.start("pronoun")
                end = match.end("pronoun")
                if (start, end) in seen_spans:
                    continue
                text = value[start:end]
                features = cls.pronoun_agreement(text)
                if features is None:
                    continue
                seen_spans.add((start, end))
                found.append(
                    SurfacePronounMention(
                        text=text,
                        start=start,
                        end=end,
                        gender=features[0],
                        number=features[1],
                    )
                )
        found.sort(key=lambda item: item.start)
        return tuple(found)

    @classmethod
    def pronoun_agreement(cls, mention: str) -> tuple[str, str] | None:
        normalized = cls.normalize(mention).strip()
        return cls._PRONOUNS.get(normalized) or {
            "he": ("masculine", "singular"),
            "she": ("feminine", "singular"),
            "they": ("masculine", "plural"),
            # Dative clitics encode number but do not identify grammatical gender.
            "le": ("unknown", "singular"),
            "les": ("unknown", "plural"),
        }.get(normalized)

    @classmethod
    def grammatical_features(
        cls,
        text: str,
        alias: str,
    ) -> tuple[str | None, str | None]:
        """Read explicit local article/apposition agreement, never properties of a name."""
        if not isinstance(text, str) or not isinstance(alias, str) or not alias.strip():
            return None, None
        articles = "|".join(sorted(cls._ARTICLES, key=len, reverse=True))
        pattern = (
            r"(?<!\w)(?P<article>" + articles
            + r")\s+(?:(?P<head>[\wáéíóúüñ]+)\s+)?"
            + re.escape(alias.strip()) + r"(?!\w)"
        )
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            head = match.group("head")
            if head and cls.normalize(head) not in cls._HUMAN_HEADS:
                continue
            return cls._ARTICLES[cls.normalize(match.group("article"))]
        return None, None
