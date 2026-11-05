from __future__ import annotations

from typing import Any, ClassVar


class ContextRanker:
    """
    Responsable exclusivamente de calcular relevancia
    y puntuación de candidatos de contexto.

    No conoce WorldState.
    No realiza búsquedas.
    No expande el grafo.
    No construye texto.

    Su responsabilidad es transformar:

        candidato + query + relevancia base

    en:

        score
    """

    DIRECT_ENTITY_RELEVANCE = 1.0
    RELATED_ENTITY_RELEVANCE = 0.7

    DIRECT_MATCH_BONUS = 0.25

    DEFAULT_RELATION_RELEVANCE = 0.70

    RELATION_RELEVANCE_WEIGHTS: ClassVar[dict[str, float]] = {
        # Relaciones sociales / narrativas fuertes
        "friend": 1.00,
        "friendship": 1.00,
        "ally": 1.00,
        "alliance": 1.00,
        "family": 1.00,
        "parent": 1.00,
        "child": 1.00,

        # Relaciones hostiles
        "enemy": 0.95,
        "rival": 0.90,
        "hostile": 0.90,

        # Relaciones de pertenencia / proximidad
        "owner": 0.90,
        "owns": 0.90,
        "member": 0.85,
        "member_of": 0.85,

        # Relaciones espaciales
        "lives_in": 0.75,
        "located_in": 0.75,
        "resident_of": 0.75,

        # Relaciones débiles
        "knows": 0.65,
        "met": 0.60,
        "works_with": 0.80,
    }

    def get_relation_relevance(
        self,
        relation_type: Any,
    ) -> float:
        """
        Devuelve el peso de propagación de una relación.

        La comparación es case-insensitive y tolera valores
        no string.
        """

        if relation_type is None:
            return self.DEFAULT_RELATION_RELEVANCE

        normalized = str(
            relation_type
        ).strip().casefold()

        if not normalized:
            return self.DEFAULT_RELATION_RELEVANCE

        return self.RELATION_RELEVANCE_WEIGHTS.get(
            normalized,
            self.DEFAULT_RELATION_RELEVANCE,
        )

    def entity_context_score(
        self,
        entity: dict[str, Any],
        query: str,
    ) -> float:
        """
        Conserva la relevancia relacional calculada previamente
        y añade una pequeña bonificación por coincidencia directa.
        """

        relevance = entity.get(
            "_relevance",
            self.DIRECT_ENTITY_RELEVANCE,
        )

        try:
            relevance = float(relevance)
        except (TypeError, ValueError):
            relevance = self.DIRECT_ENTITY_RELEVANCE

        return (
            relevance
            + self.direct_match_bonus(
                entity,
                query,
            )
        )

    def direct_match_bonus(
        self,
        data: dict[str, Any],
        query: str,
    ) -> float:
        """
        Añade una pequeña bonificación cuando la consulta aparece
        directamente en los datos del candidato.
        """

        if not query:
            return 0.0

        normalized_query = query.casefold()

        searchable_fields = (
            "name",
            "description",
            "title",
            "notes",
            "significance",
            "relation_type",
            "event_type",
            "resource_type",
            "unit",
        )

        for field in searchable_fields:
            value = data.get(field)

            if value is None:
                continue

            if normalized_query in str(value).casefold():
                return self.DIRECT_MATCH_BONUS

        return 0.0

    def score_candidate(
        self,
        data: dict[str, Any],
        query: str,
        base_score: float,
    ) -> float:
        """
        Calcula la puntuación final de un candidato estructurado.

        La puntuación combina:

        - relevancia relacional de la entidad, cuando existe;
        - score base de la categoría;
        - bonus por coincidencia directa.

        Para entidades que contienen `_relevance`, esa relevancia
        sustituye al score base de la categoría.
        """

        score = float(base_score)

        if "_relevance" in data:
            relevance = data.get(
                "_relevance",
                self.DIRECT_ENTITY_RELEVANCE,
            )

            try:
                relevance = float(relevance)
            except (TypeError, ValueError):
                relevance = self.DIRECT_ENTITY_RELEVANCE

            score = relevance

        score += self.direct_match_bonus(
            data,
            query,
        )

        return score

    def score_context_candidate(
        self,
        text: str,
        query: str,
        base_score: float,
    ) -> float:
        """
        Calcula la puntuación de un candidato textual.

        Mantiene la regla existente:
        - score base
        - bonus si algún término de la query aparece
          en el texto del candidato.

        La query puede contener varias palabras.
        """

        if not query:
            return base_score

        normalized_text = str(text).casefold()
        normalized_query = str(query).casefold()

        words = [
            word
            for word in normalized_query.split()
            if word
        ]

        if not words:
            return base_score

        matches = sum(
            1
            for word in words
            if word in normalized_text
        )

        if matches == 0:
            return base_score

        return (
            base_score
            + self.DIRECT_MATCH_BONUS
            * matches
        )