"""
Ollama API adapter implementation.

Handles Ollama-specific API calls with structured JSON schema output.
Uses Ollama's native structured output support via the `format` parameter.
"""

import time
import logging
from typing import Type
from pydantic import BaseModel

from openai.types.responses.parsed_response import ParsedResponse


from .LLMClient import LLMClient
from dglink.core.constants import open_ai_client

logger = logging.getLogger(__name__)
REASONING_MODELS = {"gpt-5", "gpt-5-mini", "o1", "o3", "o3-mini", "o4-mini"}


class openAIClient(LLMClient):
    """
    Ollama implementation of LLM client adapter.
    """

    def __init__(
        self,
        model: str = "gpt-5-mini",
    ):
        self.model: str = model
        self.provider = "openAI"
        self.reasoning_model = self.model in REASONING_MODELS

    def structured_call(
        self,
        context: str,
        user_prompt: str,
        schema: Type[BaseModel],
        max_retries: int = 3,
        retry_delay: float = 1.0,
        temperature: float | None = 0.0,
    ) -> BaseModel:
        """
        Make an LLM API call with structured pydantic response format
        """
        num_retries = 0
        response = None
        ## temperature not used in reasoning models so by pass in that case.
        temperature = temperature if not self.reasoning_model else None
        while num_retries < max_retries:
            try:
                response = open_ai_client.responses.parse(
                    model=self.model,
                    input=[
                        {
                            "role": "system",
                            "content": context,
                        },
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=None,
                    text_format=schema,
                )
                break
            except:
                logger.info(f"{self.provider} call failed retrying...")
                num_retries += 1
                time.sleep(retry_delay)
        assert isinstance(
            response, ParsedResponse
        ), f"No valid response after {num_retries} retries..."
        output = response.output_parsed
        assert isinstance(output, BaseModel)
        return output
