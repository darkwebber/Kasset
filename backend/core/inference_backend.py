"""
inference_backend.py — Abstract interface for inference backends.

Defines the contract that any model backend must implement.
This enables swapping MLX for Ollama, vLLM, remote APIs, etc.
without touching agent.py or api.py.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Generator, Optional


class InferenceBackend(ABC):
    """Abstract base for all inference backends."""

    @abstractmethod
    def load_model(self) -> None:
        """Load the model into memory."""
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        """Return True if model is loaded and ready for inference."""
        ...

    @abstractmethod
    def model_status(self) -> dict:
        """Return a status dict: {status, model, error?, load_time_s?}."""
        ...

    @abstractmethod
    def stream_generate(
        self,
        messages: List[Dict],
        image: Optional[str] = None,
        max_tokens: int = 4096,
        thinking: bool = True,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> Generator[str, None, None]:
        """Yield text chunks as they are generated."""
        ...

    @abstractmethod
    def generate(
        self,
        messages: List[Dict],
        image_filepath: Optional[str] = None,
        max_tokens: int = 4096,
        thinking: bool = True,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> str:
        """Non-streaming generation. Returns the full response text."""
        ...

    def cleanup_temp_files(self) -> None:
        """Clean up any temporary files created during inference. Optional."""
        pass

    @staticmethod
    def list_available_models() -> List[Dict[str, Any]]:
        """List models available to this backend. Optional."""
        return []
