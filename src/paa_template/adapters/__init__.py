"""Provider adapter boundary."""

from .loader import load_model_adapter
from .mock import MockAdapter
from .openai_compatible import OpenAICompatibleAdapter

__all__ = ["MockAdapter", "OpenAICompatibleAdapter", "load_model_adapter"]
