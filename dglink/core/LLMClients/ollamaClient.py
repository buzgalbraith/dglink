"""
Ollama API adapter implementation.

Handles Ollama-specific API calls with structured JSON schema output.
Uses Ollama's native structured output support via the `format` parameter.
"""

import time
import logging
from typing import Type
from pydantic import BaseModel

from ollama import chat, ChatResponse


from .LLMClient import LLMClient

logger = logging.getLogger(__name__)


class ollamaClient(LLMClient):
    """
    Ollama implementation of LLM client adapter.
    """

    def __init__(
        self,
        model: str = "gpt-oss:20b",
    ):
        self.model: str = model
        self.provider = "ollama"

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
        num_retries = 0
        messages = [
            {"role": "system", "content": context},
            {"role": "user", "content": user_prompt},
        ]
        response = None
        while num_retries < max_retries:
            try:
                response = chat(
                    model=self.model,
                    messages=messages,
                    format=schema.model_json_schema(),
                    options={
                        "temperature": temperature,
                    },
                )
                break
            except:
                logger.info(f"{self.provider} call failed retrying...")
                num_retries += 1
                time.sleep(retry_delay)
        assert isinstance(
            response, ChatResponse
        ), f"No valid response after {num_retries} retries..."
        raw_res = response.message.content
        assert isinstance(raw_res, str)
        return schema.model_validate_json(raw_res)
