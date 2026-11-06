from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProviderError(RuntimeError):
    """Error base para proveedores LLM."""


class LLMProvider(ABC):
    """
    Contrato mínimo para cualquier proveedor LLM.

    El resto de la aplicación no debe conocer si el modelo
    está en Ollama, OpenAI, Grok, etc.

    Contrato:

        prompt -> respuesta textual

    El proveedor NO debe:
    - modificar WorldState
    - ejecutar operaciones
    - persistir memoria
    - interpretar el JSON
    - conocer WorldOperation
    """

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """
        Genera una respuesta textual a partir de un prompt.
        """

        raise NotImplementedError

    def __call__(self, prompt: str) -> str:
        """
        Permite utilizar el provider como Callable.

        Esto mantiene compatibilidad con LLMWorldExtractor,
        que actualmente recibe un callable.
        """

        return self.generate(prompt)



__all__ = [
    "LLMProvider",
    "LLMProviderError",
]
