from __future__ import annotations

import re
from typing import Any

from models.world_state import WorldState


class MemorySearchService:
    """
    Busca información relevante dentro del WorldState.

    Este servicio solamente recupera información.
    No modifica el mundo y no decide cómo debe presentarse
    finalmente el contexto al LLM.
    """

    def search(
        self,
        world: WorldState,
        query: str,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Busca candidatos que coinciden con una consulta dentro del WorldState.

        La búsqueda es deliberadamente sencilla y determinista.
        Se mantiene separada de la construcción final del contexto.
        """

        if not isinstance(world, WorldState):
            raise TypeError(
                "world must be a WorldState"
            )

        if not isinstance(query, str):
            raise TypeError(
                "query must be a string"
            )

        query = query.strip()

        if not query:
            return {
                "entities": [],
                "items": [],
                "item_instances": [],
                "resources": [],
                "resource_balances": [],
                "relations": [],
                "events": [],
            }

        return {
            "entities": self._search_entities(
                world,
                query,
            ),
            "items": self._search_items(
                world,
                query,
            ),
            "item_instances": self._search_item_instances(
                world,
                query,
            ),
            "resources": self._search_resources(
                world,
                query,
            ),
            "resource_balances": self._search_resource_balances(
                world,
                query,
            ),
            "relations": self._search_relations(
                world,
                query,
            ),
            "events": self._search_events(
                world,
                query,
            ),
        }

    # ------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_world(
        world: WorldState,
    ) -> None:
        if not isinstance(world, WorldState):
            raise TypeError(
                "world must be a WorldState"
            )

    # ------------------------------------------------------------------
    # EXPORT
    # ------------------------------------------------------------------

    def export(
        self,
        world: WorldState,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Exporta únicamente el estado público del mundo.

        Reglas:
        - entidades inactivas no se exportan;
        - relaciones inactivas no se exportan;
        - eventos secretos no se exportan;
        - los objetos restantes se serializan sin modificar WorldState.
        """

        self._validate_world(world)

        return {
            "entities": [
                self._serialize(entity)
                for entity in world.entities.values()
                if getattr(
                    entity,
                    "active",
                    True,
                )
            ],
            "items": [
                self._serialize(item)
                for item in world.items.values()
                if getattr(
                    item,
                    "active",
                    True,
                )
            ],
            "item_instances": [
                self._serialize(instance)
                for instance in world.item_instances.values()
                if getattr(
                    instance,
                    "active",
                    True,
                )
            ],
            "resources": [
                self._serialize(resource)
                for resource in world.resources.values()
                if getattr(
                    resource,
                    "active",
                    True,
                )
            ],
            "resource_balances": [
                self._serialize(balance)
                for balance in world.resource_balances.values()
                if getattr(
                    balance,
                    "active",
                    True,
                )
            ],
            "relations": [
                self._serialize(relation)
                for relation in world.relations.values()
                if getattr(
                    relation,
                    "active",
                    True,
                )
            ],
            "events": [
                self._serialize(event)
                for event in world.events.values()
                if not getattr(
                    event,
                    "secret",
                    False,
                )
                and getattr(
                    event,
                    "active",
                    True,
                )
            ],
        }

    # ------------------------------------------------------------------
    # ENTITIES
    # ------------------------------------------------------------------

    def _search_entities(
        self,
        world: WorldState,
        query: str,
    ) -> list[dict[str, Any]]:
        results = []

        for entity in world.entities.values():
            if not getattr(entity, "active", True):
                continue

            if self._matches(
                query,
                getattr(entity, "name", None),
                getattr(entity, "entity_type", None),
                getattr(entity, "description", None),
                getattr(entity, "notes", None),
                getattr(entity, "metadata", None),
            ):
                results.append(
                    self._serialize(
                        entity
                    )
                )

        return results

    # ------------------------------------------------------------------
    # ITEMS
    # ------------------------------------------------------------------

    def _search_items(
        self,
        world: WorldState,
        query: str,
    ) -> list[dict[str, Any]]:
        results = []

        for item in world.items.values():
            if self._matches(
                query,
                getattr(item, "name", None),
                getattr(item, "item_type", None),
                getattr(item, "description", None),
                getattr(item, "notes", None),
                getattr(item, "metadata", None),
            ):
                results.append(
                    self._serialize(
                        item
                    )
                )

        return results

    # ------------------------------------------------------------------
    # ITEM INSTANCES
    # ------------------------------------------------------------------

    def _search_item_instances(
        self,
        world: WorldState,
        query: str,
    ) -> list[dict[str, Any]]:
        results = []

        for instance in world.item_instances.values():
            if self._matches(
                query,
                getattr(instance, "item_id", None),
                getattr(instance, "owner_id", None),
                getattr(instance, "quantity", None),
                getattr(instance, "notes", None),
                getattr(instance, "metadata", None),
            ):
                results.append(
                    self._serialize(
                        instance
                    )
                )

        return results

    # ------------------------------------------------------------------
    # RESOURCES
    # ------------------------------------------------------------------

    def _search_resources(
        self,
        world: WorldState,
        query: str,
    ) -> list[dict[str, Any]]:
        results = []

        for resource in world.resources.values():
            if self._matches(
                query,
                getattr(resource, "name", None),
                getattr(resource, "resource_type", None),
                getattr(resource, "description", None),
                getattr(resource, "notes", None),
                getattr(resource, "metadata", None),
            ):
                results.append(
                    self._serialize(
                        resource
                    )
                )

        return results

    # ------------------------------------------------------------------
    # RESOURCE BALANCES
    # ------------------------------------------------------------------

    def _search_resource_balances(
        self,
        world: WorldState,
        query: str,
    ) -> list[dict[str, Any]]:
        results = []

        for balance in world.resource_balances.values():
            if self._matches(
                query,
                getattr(balance, "resource_id", None),
                getattr(balance, "owner_id", None),
                getattr(balance, "amount", None),
                getattr(balance, "notes", None),
            ):
                results.append(
                    self._serialize(
                        balance
                    )
                )

        return results

    # ------------------------------------------------------------------
    # RELATIONS
    # ------------------------------------------------------------------

    def _search_relations(
        self,
        world: WorldState,
        query: str,
    ) -> list[dict[str, Any]]:
        results = []

        for relation in world.relations.values():
            if self._matches(
                query,
                getattr(relation, "relation_type", None),
                getattr(relation, "source_id", None),
                getattr(relation, "target_id", None),
                getattr(relation, "description", None),
                getattr(relation, "notes", None),
                getattr(relation, "metadata", None),
            ):
                results.append(
                    self._serialize(
                        relation
                    )
                )

        return results

    # ------------------------------------------------------------------
    # EVENTS
    # ------------------------------------------------------------------

    def _search_events(
        self,
        world: WorldState,
        query: str,
    ) -> list[dict[str, Any]]:
        results = []

        for event in world.events.values():

            # Los eventos secretos nunca deben exponerse
            # mediante búsquedas de memoria.
            if getattr(event, "secret", False):
                continue

            if self._matches(
                query,
                getattr(event, "title", None),
                getattr(event, "event_type", None),
                getattr(event, "description", None),
                getattr(event, "location", None),
                getattr(event, "participants", None),
                getattr(event, "consequences", None),
                getattr(event, "metadata", None),
            ):
                results.append(
                    self._serialize(
                        event
                    )
                )

        return results

    # ------------------------------------------------------------------
    # MATCHING
    # ------------------------------------------------------------------

    @classmethod
    def _matches(
        cls,
        query: str,
        *values: Any,
    ) -> bool:
        """
        Comprueba si una consulta coincide con alguno de los valores
        indexables.

        Se soportan dos niveles:

        1. Coincidencia de la consulta completa.
        2. Coincidencia de términos significativos.

        El segundo nivel permite consultas naturales como:

            ¿Quién es Aldren?
            Háblame de Aldren
            Dónde está Aldren
            ¿Qué sabes sobre Aldren?

        sin convertir el buscador en un sistema semántico.
        """

        normalized_query = str(
            query
        ).strip().casefold()

        if not normalized_query:
            return False

        searchable_values: list[str] = []

        for value in values:
            searchable_values.extend(
                cls._flatten_value(
                    value
                )
            )

        if not searchable_values:
            return False

        # --------------------------------------------------------------
        # Coincidencia exacta/parcial de la consulta completa
        # --------------------------------------------------------------

        for value in searchable_values:
            if normalized_query in value:
                return True

        # --------------------------------------------------------------
        # Coincidencia por términos significativos
        # --------------------------------------------------------------

        terms = cls._extract_query_terms(
            normalized_query
        )

        if not terms:
            return False

        for value in searchable_values:
            for term in terms:
                if term in value:
                    return True

        return False

    @staticmethod
    def _flatten_value(
        value: Any,
    ) -> list[str]:
        """
        Convierte valores arbitrarios en texto indexable.
        """

        if value is None:
            return []

        if isinstance(value, dict):
            result = []

            for key, item in value.items():
                result.extend(
                    MemorySearchService._flatten_value(
                        key
                    )
                )
                result.extend(
                    MemorySearchService._flatten_value(
                        item
                    )
                )

            return result

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            result = []

            for item in value:
                result.extend(
                    MemorySearchService._flatten_value(
                        item
                    )
                )

            return result

        return [
            str(value).casefold()
        ]

    @staticmethod
    def _extract_query_terms(
        query: str,
    ) -> list[str]:
        """
        Extrae palabras relevantes de una consulta natural.

        No intenta interpretar semántica.
        Solamente elimina palabras funcionales frecuentes.
        """

        tokens = re.findall(
            r"[a-záéíóúüñ0-9]+",
            query.casefold(),
        )

        stopwords = {
            # Español
            "qué",
            "que",
            "quién",
            "quien",
            "quienes",
            "cuál",
            "cual",
            "cuáles",
            "cuales",
            "cómo",
            "como",
            "dónde",
            "donde",
            "cuándo",
            "cuando",
            "por",
            "para",
            "sobre",
            "entre",
            "con",
            "sin",
            "del",
            "las",
            "los",
            "una",
            "uno",
            "unos",
            "unas",
            "este",
            "esta",
            "estos",
            "estas",
            "eso",
            "esa",
            "ese",
            "es",
            "son",
            "hay",
            "me",
            "te",
            "se",
            "de",
            "el",
            "la",
            "y",
            "o",
            "a",
            "en",

            # Inglés
            "what",
            "who",
            "whom",
            "which",
            "where",
            "when",
            "how",
            "about",
            "with",
            "from",
            "this",
            "that",
            "these",
            "those",
            "the",
            "and",
            "or",
            "is",
            "are",
            "am",
            "an",
            "of",
            "to",
            "in",
            "on",
            "for",
            "you",
            "it",
        }

        return [
            token
            for token in tokens
            if len(token) >= 3
            and token not in stopwords
        ]

    # ------------------------------------------------------------------
    # SERIALIZACIÓN
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize(
        value: Any,
    ) -> dict[str, Any]:
        """
        Convierte modelos/dataclasses/diccionarios a la representación
        que consume el resto del sistema.
        """

        if isinstance(value, dict):
            return dict(value)

        if hasattr(
            value,
            "model_dump",
        ):
            return value.model_dump()

        if hasattr(
            value,
            "dict",
        ):
            return value.dict()

        if hasattr(
            value,
            "__dict__",
        ):
            return dict(
                value.__dict__
            )

        return {
            "value": value
        }