from __future__ import annotations

from typing import Any, ClassVar

from models.turn_record import TurnRecord
from services.context_ranker import ContextRanker


class ContextRenderer:
    """Builds ranked textual context while respecting independent budgets."""

    CATEGORY_BASE_SCORES: ClassVar[dict[str, float]] = {
        "entities": 1.00,
        "relations": 0.80,
        "events": 0.70,
        "items": 0.60,
        "item_instances": 0.50,
        "resources": 0.40,
        "resource_balances": 0.30,
        "recent_turns": 0.90,
    }

    CATEGORY_PRIORITY: ClassVar[dict[str, int]] = {
        "entities": 0,
        "relations": 1,
        "events": 2,
        "items": 3,
        "item_instances": 4,
        "resources": 5,
        "resource_balances": 6,
        "recent_turns": 0,
    }

    def __init__(
        self,
        ranker: ContextRanker,
        max_context_chars: int,
        max_recent_turns_chars: int,
    ) -> None:
        self.ranker = ranker
        self.max_context_chars = max_context_chars
        self.max_recent_turns_chars = max_recent_turns_chars

    # ============================================================
    # TEXT CONTEXT
    # ============================================================

    def _build_text_context(
        self,
        result: dict[str, Any],
    ) -> str:
        """
        Construye el contexto textual final.

        El contexto estructurado y el historial reciente
        tienen presupuestos independientes.

        Presupuesto estructurado:
            self.max_context_chars

        Presupuesto historial:
            self.max_recent_turns_chars

        De esta forma una conversación larga no puede expulsar
        completamente del contexto a las entidades, relaciones,
        eventos y demás información persistente del mundo.
        """

        query = str(
            result.get(
                "query",
                "",
            )
        ).strip().casefold()

        candidates = (
            self._build_context_candidates(
                result,
                query,
            )
        )

        structured_candidates = [
            candidate
            for candidate in candidates
            if candidate["category"]
            != "recent_turns"
        ]

        recent_turn_candidates = [
            candidate
            for candidate in candidates
            if candidate["category"]
            == "recent_turns"
        ]

        structured_context = (
            self._render_candidates_with_budget(
                structured_candidates,
                self.max_context_chars,
            )
        )

        recent_turns_context = (
            self._render_candidates_with_budget(
                recent_turn_candidates,
                self.max_recent_turns_chars,
            )
        )

        sections = []

        if structured_context:
            sections.append(
                structured_context
            )

        if recent_turns_context:
            sections.append(
                self._category_header(
                    "recent_turns"
                )
                + "\n"
                + recent_turns_context
            )

        if not sections:
            return "Sin información relevante."

        return "\n\n".join(sections)

    def _render_candidates_with_budget(
        self,
        candidates: list[dict[str, Any]],
        max_chars: int,
    ) -> str:
        """
        Selecciona y renderiza candidatos respetando
        un presupuesto independiente.

        El método no modifica los candidatos originales.
        """

        if not candidates:
            return ""

        candidates = list(candidates)

        candidates.sort(
            key=lambda candidate: (
                -candidate["score"],
                candidate["category_order"],
                candidate["index"],
            )
        )

        selected: list[dict[str, Any]] = []

        current_length = 0
        selected_categories: set[str] = set()

        for candidate in candidates:

            category = candidate["category"]
            text = candidate["text"]

            header = self._category_header(
                category
            )

            additional_length = len(text)

            if current_length > 0:
                additional_length += 1

            if category not in selected_categories:

                additional_length += len(header)

                if current_length > 0:
                    additional_length += 1

            projected_length = (
                current_length
                + additional_length
            )

            if projected_length > max_chars:
                continue

            selected.append(candidate)

            current_length = projected_length

            selected_categories.add(
                category
            )

        if not selected:
            return ""

        selected.sort(
            key=lambda candidate: (
                candidate["category_order"],
                candidate["index"],
                -candidate["score"],
            )
        )

        return self._render_selected_candidates(
            selected
        )

    # ============================================================
    # CONTEXT CANDIDATES
    # ============================================================

    def _build_context_candidates(
        self,
        result: dict[str, Any],
        query: str,
    ) -> list[dict[str, Any]]:
        """
        Convierte la información disponible en candidatos
        independientes de contexto.

        Cada candidato contiene:

            category
            text
            score
            category_order
            index

        Importante:

        Este método es de instancia porque utiliza
        self.ranker.
        """

        candidates: list[dict[str, Any]] = []

        category_definitions = [
            (
                "entities",
                self.CATEGORY_BASE_SCORES["entities"],
                self.CATEGORY_PRIORITY["entities"],
                self._entity_lines,
            ),
            (
                "relations",
                self.CATEGORY_BASE_SCORES["relations"],
                self.CATEGORY_PRIORITY["relations"],
                self._relation_lines,
            ),
            (
                "events",
                self.CATEGORY_BASE_SCORES["events"],
                self.CATEGORY_PRIORITY["events"],
                self._event_lines,
            ),
            (
                "items",
                self.CATEGORY_BASE_SCORES["items"],
                self.CATEGORY_PRIORITY["items"],
                self._item_lines,
            ),
            (
                "item_instances",
                self.CATEGORY_BASE_SCORES["item_instances"],
                self.CATEGORY_PRIORITY["item_instances"],
                self._item_instance_lines,
            ),
            (
                "resources",
                self.CATEGORY_BASE_SCORES["resources"],
                self.CATEGORY_PRIORITY["resources"],
                self._resource_lines,
            ),
            (
                "resource_balances",
                self.CATEGORY_BASE_SCORES["resource_balances"],
                self.CATEGORY_PRIORITY["resource_balances"],
                self._resource_balance_lines,
            ),
        ]

        for (
            category,
            base_score,
            category_order,
            line_builder,
        ) in category_definitions:

            values = result.get(
                category,
                [],
            )

            if not isinstance(
                values,
                list,
            ):
                continue

            for index, value in enumerate(values):

                if not isinstance(
                    value,
                    dict,
                ):
                    continue

                lines = line_builder(
                    [value]
                )

                if not lines:
                    continue

                text = lines[0]

                score = self.ranker.score_candidate(
                    data=value,
                    query=query,
                    base_score=base_score,
                )

                candidates.append(
                    {
                        "category": category,
                        "text": text,
                        "score": score,
                        "category_order": category_order,
                        "index": index,
                    }
                )

        recent_turns = result.get(
            "recent_turns",
            [],
        )

        if isinstance(
            recent_turns,
            list,
        ):
            history_category = "recent_turns"

            history_base_score = (
                self.CATEGORY_BASE_SCORES.get(
                    history_category,
                    0.0,
                )
            )

            history_category_order = (
                self.CATEGORY_PRIORITY.get(
                    history_category,
                    len(category_definitions),
                )
            )

            for index, turn in enumerate(
                recent_turns
            ):
                if not isinstance(
                    turn,
                    TurnRecord,
                ):
                    continue

                text = (
                    f"Jugador: {turn.player_input}\n"
                    f"DM: {turn.narrative}"
                )

                score = self.ranker.score_candidate(
                    data={
                        "player_input": turn.player_input,
                        "narrative": turn.narrative,
                    },
                    query=query,
                    base_score=history_base_score,
                )

                candidates.append(
                    {
                        "category": history_category,
                        "text": text,
                        "score": score,
                        "category_order": history_category_order,
                        "index": index,
                    }
                )

        return candidates

    # ============================================================
    # CANDIDATE LINE BUILDERS
    # ============================================================

    @staticmethod
    def _entity_lines(
        entities: list[dict[str, Any]],
    ) -> list[str]:

        lines: list[str] = []

        for entity in entities:

            name = entity.get(
                "name",
                "Sin nombre",
            )

            entity_type = entity.get(
                "entity_type",
                "unknown",
            )

            description = entity.get(
                "description",
                "",
            )

            notes = entity.get(
                "notes",
                "",
            )

            line = (
                f"- {name} "
                f"({entity_type})"
            )

            if description:
                line += (
                    f": {description}"
                )

            if notes:
                line += (
                    f" Notas: {notes}"
                )

            lines.append(line)

        return lines

    @staticmethod
    def _relation_lines(
        relations: list[dict[str, Any]],
    ) -> list[str]:

        lines: list[str] = []

        for relation in relations:

            relation_type = relation.get(
                "relation_type",
                "unknown",
            )

            subject_id = relation.get(
                "subject_id"
            )

            target_id = relation.get(
                "target_id"
            )

            line = (
                f"- {relation_type}: "
                f"{subject_id} -> "
                f"{target_id}"
            )

            metadata = relation.get(
                "metadata"
            )

            if isinstance(
                metadata,
                dict,
            ):

                reason = metadata.get(
                    "reason"
                )

                if reason:
                    line += (
                        f" Motivo: {reason}"
                    )

            lines.append(line)

        return lines

    @staticmethod
    def _event_lines(
        events: list[dict[str, Any]],
    ) -> list[str]:

        lines: list[str] = []

        for event in events:

            title = event.get(
                "title",
                "Sin título",
            )

            description = event.get(
                "description",
                "",
            )

            consequences = event.get(
                "consequences",
                "",
            )

            line = f"- {title}"

            if description:
                line += (
                    f": {description}"
                )

            if consequences:
                line += (
                    f" Consecuencias: "
                    f"{consequences}"
                )

            lines.append(line)

        return lines

    @staticmethod
    def _item_lines(
        items: list[dict[str, Any]],
    ) -> list[str]:

        lines: list[str] = []

        for item in items:

            name = item.get(
                "name",
                "Sin nombre",
            )

            description = item.get(
                "description",
                "",
            )

            significance = item.get(
                "significance",
                "",
            )

            notes = item.get(
                "notes",
                "",
            )

            line = f"- {name}"

            if description:
                line += (
                    f": {description}"
                )

            if significance:
                line += (
                    f" Importancia: "
                    f"{significance}"
                )

            if notes:
                line += (
                    f" Notas: {notes}"
                )

            lines.append(line)

        return lines

    @staticmethod
    def _item_instance_lines(
        instances: list[dict[str, Any]],
    ) -> list[str]:

        lines: list[str] = []

        for instance in instances:

            instance_id = instance.get(
                "id",
                "unknown",
            )

            item_id = instance.get(
                "item_id"
            )

            owner_id = instance.get(
                "owner_id"
            )

            location_id = instance.get(
                "location_id"
            )

            line = (
                f"- Instancia "
                f"{instance_id}"
            )

            if item_id is not None:
                line += (
                    f" item={item_id}"
                )

            if owner_id is not None:
                line += (
                    f" propietario="
                    f"{owner_id}"
                )

            if location_id is not None:
                line += (
                    f" ubicación="
                    f"{location_id}"
                )

            lines.append(line)

        return lines

    @staticmethod
    def _resource_lines(
        resources: list[dict[str, Any]],
    ) -> list[str]:

        lines: list[str] = []

        for resource in resources:

            name = resource.get(
                "name",
                "Sin nombre",
            )

            resource_type = resource.get(
                "resource_type",
                "",
            )

            unit = resource.get(
                "unit",
                "",
            )

            notes = resource.get(
                "notes",
                "",
            )

            line = f"- {name}"

            if resource_type:
                line += (
                    f" ({resource_type})"
                )

            if unit:
                line += (
                    f" Unidad: {unit}"
                )

            if notes:
                line += (
                    f" Notas: {notes}"
                )

            lines.append(line)

        return lines

    @staticmethod
    def _resource_balance_lines(
        balances: list[dict[str, Any]],
    ) -> list[str]:

        lines: list[str] = []

        for balance in balances:

            balance_id = balance.get(
                "id",
                "unknown",
            )

            resource_id = balance.get(
                "resource_id"
            )

            owner_id = balance.get(
                "owner_id"
            )

            amount = balance.get(
                "amount"
            )

            line = (
                f"- Balance "
                f"{balance_id}"
            )

            if resource_id is not None:
                line += (
                    f" recurso="
                    f"{resource_id}"
                )

            if owner_id is not None:
                line += (
                    f" propietario="
                    f"{owner_id}"
                )

            if amount is not None:
                line += (
                    f" cantidad="
                    f"{amount}"
                )

            lines.append(line)

        return lines

    # ============================================================
    # CATEGORY HELPERS
    # ============================================================

    @staticmethod
    def _category_header(
        category: str,
    ) -> str:
        """
        Devuelve el encabezado público de una categoría.
        """

        headers = {
            "entities": "[ENTIDADES]",
            "relations": "[RELACIONES]",
            "events": "[EVENTOS]",
            "items": "[OBJETOS]",
            "item_instances": "[INSTANCIAS DE OBJETOS]",
            "resources": "[RECURSOS]",
            "resource_balances": "[BALANCES DE RECURSOS]",
            "recent_turns": "HISTORIAL RECIENTE",
        }

        return headers.get(
            category,
            f"[{category.upper()}]",
        )

    # ============================================================
    # CONTEXT RENDERING
    # ============================================================

    def _render_selected_candidates(
        self,
        candidates: list[dict[str, Any]],
    ) -> str:
        """
        Renderiza los candidatos seleccionados agrupándolos
        por categoría.

        Este método es de instancia porque utiliza
        self._category_header().
        """

        if not candidates:
            return "Sin información relevante."

        sections: list[str] = []

        current_category: str | None = None

        for candidate in candidates:

            category = candidate["category"]

            if category != current_category:

                sections.append(
                    self._category_header(
                        category
                    )
                )

                current_category = category

            sections.append(
                candidate["text"]
            )

        return "\n".join(
            sections
        )

    @staticmethod
    def _strip_internal_context_fields(
        result: dict[str, Any],
    ) -> None:
        """
        Elimina metadatos internos de relevancia antes de devolver
        el resultado público.
        """

        for entity in result.get(
            "entities",
            [],
        ):

            if not isinstance(
                entity,
                dict,
            ):
                continue

            entity.pop(
                "_relevance",
                None,
            )

            entity.pop(
                "_depth",
                None,
            )

    @staticmethod
    def _build_recent_turns_context(
        recent_turns: list[TurnRecord],
    ) -> str:
        if not recent_turns:
            return ""

        lines = [
            "=== HISTORIAL RECIENTE ==="
        ]

        for turn in recent_turns:
            player_input = turn.player_input.strip()
            narrative = turn.narrative.strip()

            if not player_input and not narrative:
                continue

            if player_input:
                lines.append(
                    f"Jugador: {player_input}"
                )

            if narrative:
                lines.append(
                    f"DM: {narrative}"
                )

        if len(lines) == 1:
            return ""

        return "\n".join(lines)
