from __future__ import annotations

from typing import Any, ClassVar

from models.turn_record import TurnRecord
from models.world_context_projection import WorldContextProjection
from models.world_state import WorldState

from .context_expander import ContextExpander
from .context_ranker import ContextRanker
from .context_renderer import ContextRenderer
from .memory_search_service import MemorySearchService
from .proposal_context_selector import ProposalContextSelector


class ContextBuilder:
    """
    Construye el contexto narrativo para el LLM.

    El proceso se divide en dos fases:

    1. Reunir y enriquecer información estructurada relevante.
    2. Convertir esa información en contexto textual limitado
       por un presupuesto.

    MemorySearchService encuentra candidatos.
    ContextExpander amplía los resultados siguiendo las
    relaciones del WorldState.
    ContextRanker calcula la relevancia de los candidatos.
    ContextRenderer convierte los datos estructurados e historial
    en texto limitado por presupuestos independientes.
    ContextBuilder valida la entrada y coordina el pipeline.

    Responsabilidades:

    - Validar la entrada.
    - Coordinar búsqueda, expansión y renderizado.
    - Mantener el contrato público del resultado.
    - No modificar WorldState.
    - No acceder directamente a SQLite.
    """

    # Se mide en caracteres, no tokens.
    DEFAULT_MAX_CONTEXT_CHARS = 6000
    DEFAULT_MAX_RECENT_TURNS_CHARS = 2000

    # ============================================================
    # CONTEXT CANDIDATE SCORING
    # ============================================================

    CATEGORY_BASE_SCORES: ClassVar[dict[str, float]] = (
        ContextRenderer.CATEGORY_BASE_SCORES
    )

    CATEGORY_PRIORITY: ClassVar[dict[str, int]] = (
        ContextRenderer.CATEGORY_PRIORITY
    )

    # ============================================================
    # INITIALIZATION
    # ============================================================

    def __init__(
        self,
        memory_search_service: MemorySearchService | None = None,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
        max_recent_turns_chars: int = DEFAULT_MAX_RECENT_TURNS_CHARS,
        ranker: ContextRanker | None = None,
        context_expander: ContextExpander | None = None,
    ) -> None:

        if not isinstance(max_context_chars, int):
            raise TypeError(
                "max_context_chars must be an integer"
            )

        if max_context_chars <= 0:
            raise ValueError(
                "max_context_chars must be > 0"
            )

        if not isinstance(
            max_recent_turns_chars,
            int,
        ):
            raise TypeError(
                "max_recent_turns_chars must be an integer"
            )

        if max_recent_turns_chars <= 0:
            raise ValueError(
                "max_recent_turns_chars must be > 0"
            )

        self.memory_search_service = (
            memory_search_service
            or MemorySearchService()
        )

        self.max_context_chars = max_context_chars

        self.max_recent_turns_chars = (
            max_recent_turns_chars
        )

        if ranker is not None and not isinstance(
            ranker,
            ContextRanker,
        ):
            raise TypeError(
                "ranker must be a ContextRanker"
            )

        self.ranker = ranker or ContextRanker()

        self.context_expander = (
            context_expander
            or ContextExpander(
                ranker=self.ranker,
            )
        )
        self.context_renderer = ContextRenderer(
            ranker=self.ranker,
            max_context_chars=self.max_context_chars,
            max_recent_turns_chars=self.max_recent_turns_chars,
        )
        self.proposal_context_selector = ProposalContextSelector(
            memory_search_service=self.memory_search_service,
            context_expander=self.context_expander,
            ranker=self.ranker,
        )

    # ============================================================
    # PUBLIC API
    # ============================================================

    def build(
        self,
        world: WorldState,
        query: str,
        recent_turns: list[TurnRecord] | None = None,
        *,
        supplemental_queries: tuple[str, ...] | list[str] = (),
    ) -> dict[str, Any]:
        """
        Construye el contexto completo para el LLM.

        Primero reúne los datos estructurados relevantes y después
        genera una representación textual respetando el presupuesto
        configurado.
        """

        self._validate_world(world)

        normalized_query = self._validate_query(query)

        normalized_recent_turns = self._validate_recent_turns(
            recent_turns
        )
        normalized_supplemental_queries = self._validate_supplemental_queries(
            supplemental_queries,
            primary_query=normalized_query,
        )

        if not normalized_query:
            return self._empty_result()

        result = self._build_context_data(
            world,
            normalized_query,
            normalized_supplemental_queries,
        )

        result["recent_turns"] = normalized_recent_turns

        result["context"] = self._build_text_context(
            result
        )

        ContextRenderer._strip_internal_context_fields(result)

        return result

    def build_proposal_context(
        self,
        world: WorldState,
        query: str,
        *,
        max_estimated_tokens: int,
        mandatory_entity_ids: tuple[int, ...] | list[int] = (),
        supplemental_queries: tuple[str, ...] | list[str] = (),
    ) -> WorldContextProjection:
        """Build a bounded typed projection for structured consequence proposals.

        This is deliberately separate from build(): narrative context and
        proposal context have different contracts and token budgets.
        """
        return self.proposal_context_selector.build(
            world,
            query,
            max_estimated_tokens=max_estimated_tokens,
            mandatory_entity_ids=mandatory_entity_ids,
            supplemental_queries=supplemental_queries,
        )
    # ============================================================
    # VALIDATION
    # ============================================================

    @staticmethod
    def _validate_supplemental_queries(
        queries: tuple[str, ...] | list[str],
        *,
        primary_query: str,
    ) -> tuple[str, ...]:
        if not isinstance(queries, (tuple, list)):
            raise TypeError("supplemental_queries must be a tuple or list")
        normalized: list[str] = []
        seen = {primary_query.casefold()} if primary_query else set()
        for query in queries:
            if not isinstance(query, str):
                raise TypeError("supplemental_queries must contain only strings")
            value = query.strip()
            if not value:
                continue
            key = value.casefold()
            if key not in seen:
                normalized.append(value)
                seen.add(key)
        return tuple(normalized)

    @staticmethod
    def _validate_recent_turns(
        recent_turns: list[TurnRecord] | None,
    ) -> list[TurnRecord]:
        if recent_turns is None:
            return []

        if not isinstance(
            recent_turns,
            list,
        ):
            raise TypeError(
                "recent_turns must be a list or None"
            )

        for turn in recent_turns:
            if not isinstance(
                turn,
                TurnRecord,
            ):
                raise TypeError(
                    "recent_turns must contain only TurnRecord objects"
                )

        return list(recent_turns)


    @staticmethod
    def _validate_world(
        world: WorldState,
    ) -> None:

        if not isinstance(world, WorldState):
            raise TypeError(
                "world must be a WorldState"
            )

    @staticmethod
    def _validate_query(
        query: str,
    ) -> str:

        if not isinstance(query, str):
            raise TypeError(
                "query must be a string"
            )

        return query.strip()

    # ============================================================
    # CONTEXT DATA
    # ============================================================

    def _build_context_data(
        self,
        world: WorldState,
        normalized_query: str,
        supplemental_queries: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """
        Construye los datos estructurados relevantes.

        Esta fase NO aplica el presupuesto textual.

        La búsqueda inicial se delega en
        MemorySearchService y la expansión de contexto
        se delega en ContextExpander.
        """

        if supplemental_queries:
            search_result = self.memory_search_service.search_many(
                world,
                (normalized_query, *supplemental_queries),
            )
        else:
            search_result = self.memory_search_service.search(
                world,
                normalized_query,
            )

        result = self.context_expander.expand(
            world,
            search_result,
        )

        result["query"] = normalized_query

        return result

    # ============================================================
    # RENDERER DELEGATES
    # ============================================================

    def _build_text_context(self, result: dict[str, Any]) -> str:
        return self.context_renderer._build_text_context(result)

    def _build_context_candidates(
        self,
        result: dict[str, Any],
        query: str,
    ) -> list[dict[str, Any]]:
        return self.context_renderer._build_context_candidates(
            result,
            query,
        )

    @staticmethod
    def _category_header(category: str) -> str:
        return ContextRenderer._category_header(category)

    def _render_selected_candidates(
        self,
        candidates: list[dict[str, Any]],
    ) -> str:
        return self.context_renderer._render_selected_candidates(candidates)

    # ============================================================
    # EMPTY RESULT
    # ============================================================

    @staticmethod
    def _empty_result() -> dict[str, Any]:

        return {
            "query": "",
            "entities": [],
            "items": [],
            "item_instances": [],
            "resources": [],
            "resource_balances": [],
            "relations": [],
            "events": [],
            "context": (
                "Sin información relevante."
            ),
        }
