"""
OpenAI API adapter implementation.

Handles OpenAI-specific API calls with structured JSON schema output.
"""

import time
import logging
from typing import Type
from pydantic import BaseModel
import os

from .llm_client import LLMClient
from ..optional_deps import import_optional
from ..timing import TIMER

logger = logging.getLogger(__name__)
REASONING_MODELS = {"gpt-5", "gpt-5-mini", "o1", "o3", "o3-mini", "o4-mini"}


class OpenAIClient(LLMClient):
    """
    Ollama implementation of LLM client adapter.
    """

    def __init__(
        self,
        model: str = "gpt-5-mini",
    ):
        OpenAI = import_optional("openai", "openai").OpenAI
        self.model: str = model
        self.provider = "openAI"
        self.reasoning_model = self.model in REASONING_MODELS
        self.client = OpenAI(
                api_key=os.environ.get("OPENAI_API_KEY"),
            )

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
        ParsedResponse = import_optional(
            "openai.types.responses.parsed_response", "openai"
        ).ParsedResponse
        num_retries = 0
        response = None
        ## temperature not used in reasoning models so by pass in that case.
        temperature = temperature if not self.reasoning_model else None
        while num_retries < max_retries:
            try:
                with TIMER.stage("llm"):
                    response = self.client.responses.parse(
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
                usage = getattr(response, "usage", None)
                TIMER.add(
                    "llm",
                    input_tokens=getattr(usage, "input_tokens", None),
                    output_tokens=getattr(usage, "output_tokens", None),
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
