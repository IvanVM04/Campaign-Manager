"""Shared lexical inventory for explicit speech predicates.

The inventory recognizes surface forms only. It never resolves speaker identity
or grants mechanics/world-write authority.
"""

from __future__ import annotations

import re

SPEECH_PREDICATE_FORMS = (
    "dice", "dicen", "dijo", "dijeron", "decía", "decian", "decían",
    "pregunta", "preguntan", "preguntó", "preguntaron", "pregunto", "preguntaba",
    "responde", "responden", "respondió", "respondieron", "respondia", "respondían",
    "contesta", "contestan", "contestó", "contestaron", "contestaba", "contestaban",
    "habla", "hablan", "habló", "hablaron", "hablaba", "hablaban",
    "susurra", "susurran", "susurró", "susurraron", "grita", "gritan", "gritó", "gritaron",
    "murmura", "murmuran", "murmuró", "murmuraron", "añade", "añaden", "añadió", "añadieron",
    "comenta", "comentan", "comentó", "comentaron", "avisa", "avisan", "avisó", "avisaron",
    "advierte", "advierten", "advirtió", "advirtieron", "advertía", "advertían",
    "explica", "explican", "explicó", "explicaron",
    "afirma", "afirman", "afirmó", "afirmaron",
    "asegura", "aseguran", "aseguró", "aseguraron",
    "declara", "declaran", "declaró", "declararon",
    "relata", "relatan", "relató", "relataron",
    "indica", "indican", "indicó", "indicaron",
    "revela", "revelan", "reveló", "revelaron",
    "informa", "informan", "informó", "informaron",
    "sostiene", "sostienen", "sostuvo", "sostuvieron",
    "confirma", "confirman", "confirmó", "confirmaron",
    "cuenta", "cuentan", "contó", "contaron",
    "says", "say", "said", "asks", "ask", "replies", "reply", "replied",
    "whispers", "whisper", "shouts", "shout", "tells", "tell", "told",
)

SPEECH_PREDICATE_ALTERNATION = "|".join(
    re.escape(value)
    for value in sorted(set(SPEECH_PREDICATE_FORMS), key=len, reverse=True)
)

COMMUNICATION_PREDICATE_PATTERN = re.compile(
    r"\b(?:"
    + SPEECH_PREDICATE_ALTERNATION
    + r"|habl\w*|convers\w*|cuent\w*|cont(?:ar|o|as|a|amos|an|é|ó|aron|aba|aban|ado|ando)|"
    + r"decir|decirlo|digo|decimos|dije|dijimos|"
    + r"pregunt\w*|respond\w*|susurr\w*|avis\w*|adviert\w*|explic\w*|"
    + r"afirm\w*|asegur\w*|declar\w*|sostuv\w*|relat\w*|indic\w*|revel\w*|inform\w*|confirm\w*"
    + r")\b",
    re.IGNORECASE,
)
