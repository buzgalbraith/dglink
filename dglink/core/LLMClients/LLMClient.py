"""
Abstract LLM client interface.

Defines the protocol for LLM API clients.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Type
from pydantic import BaseModel


class LLMClient(ABC):
    """
    Abstract base class for LLM API clients.
    """

    @abstractmethod
    def structured_call(
        self,
        context: str,
        user_prompt: str,
        schema: Type[BaseModel],
        max_retries: int = 3,
        retry_delay: float = 1.0,
        temperature: float = 0.0,
    ) -> BaseModel:
        """
        Make an LLM API call with structured pydantic response format
        """
        pass
