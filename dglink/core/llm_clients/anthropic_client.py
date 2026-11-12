"""
Claude on Amazon Bedrock adapter implementation.

Calls Bedrock's runtime ``InvokeModel`` API through boto3 with structured outputs
(``output_config.format`` = the pydantic schema as JSON schema), then validates the
reply against the schema. AWS credentials come from the normal chain (env vars,
~/.aws config/SSO/login); region from $AWS_REGION, default us-east-1.
"""

import json
import os
import time
import logging
from typing import Type
from pydantic import BaseModel

from .llm_client import LLMClient
from ..optional_deps import import_optional

logger = logging.getLogger(__name__)

DEFAULT_BEDROCK_MODEL = "global.anthropic.claude-haiku-5-5"
## Bedrock errors that retrying won't fix: bad request/model ID, no model access
NON_RETRYABLE_ERRORS = {
    "ValidationException",
    "AccessDeniedException",
    "ResourceNotFoundException",
    "UnrecognizedClientException",
}


def json_schema_for(schema: Type[BaseModel]) -> dict:
    """The pydantic model as a JSON schema that structured outputs accepts."""
    sc = schema.model_json_schema()
    ## structured outputs require it on every object, including nested ones in $defs
    for obj in [sc, *sc.get("$defs", {}).values()]:
        if obj.get("type") == "object":
            obj["additionalProperties"] = False
    return sc


class AnthropicClient(LLMClient):
    """
    Claude-on-Bedrock implementation of the LLM client adapter.
    """

    def __init__(
        self,
        model: str = DEFAULT_BEDROCK_MODEL,
        effort: str | None = None,
        max_tokens: int = 16000,
        read_timeout: float = 120.0,
    ):
        """
        Args:
            model: Bedrock model or inference-profile ID.
            effort: optional ``output_config.effort`` (low|medium|high|xhigh|max);
                None uses the model's default.
            max_tokens: per-response output cap. Thinking counts toward it, so keep
                it well above the size of the JSON answer.
            read_timeout: seconds to wait for a reply before failing the request.
        """
        boto3 = import_optional("boto3", "bedrock")
        botocore_config = import_optional("botocore.config", "bedrock")
        self.model: str = model or DEFAULT_BEDROCK_MODEL
        self.provider = "anthropic"
        self.effort = effort
        self.max_tokens = max_tokens
        ## running totals across calls, e.g. for cost estimates
        self.n_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.client = boto3.client(
            service_name="bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            config=botocore_config.Config(
                read_timeout=read_timeout,
                retries={"max_attempts": 3, "mode": "adaptive"},  # throttling/5xx
            ),
        )

    def _request_body(self, context: str, user_prompt: str, schema: Type[BaseModel]) -> dict:
        output_config = {"format": {"type": "json_schema", "schema": json_schema_for(schema)}}
        if self.effort:
            output_config["effort"] = self.effort
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.max_tokens,
            "system": context,
            "messages": [{"role": "user", "content": user_prompt}],
            "output_config": output_config,
        }

    @staticmethod
    def _parse_reply(reply: dict, schema: Type[BaseModel]) -> BaseModel:
        """Validate a Bedrock InvokeModel reply body against ``schema``."""
        stop_reason = reply.get("stop_reason")
        if stop_reason == "refusal":
            raise RuntimeError(f"refused: {reply.get('stop_details')}")
        if stop_reason == "max_tokens":
            raise RuntimeError("reply hit max_tokens")
        text = next(
            (b.get("text", "") for b in reply.get("content", []) if b.get("type") == "text"),
            "",
        )
        return schema.model_validate_json(text)

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
        Make an LLM API call with structured pydantic response format.

        ``temperature`` is accepted for interface compatibility but not sent: current
        Claude models reject non-default sampling parameters. boto3 retries throttling
        and server errors; this loop also retries refusals, truncated replies and
        replies that fail schema validation.
        """
        body = json.dumps(self._request_body(context, user_prompt, schema))
        last_error = None
        for attempt in range(max_retries):
            try:
                response = self.client.invoke_model(modelId=self.model, body=body)
                reply = json.loads(response["body"].read())
                usage = reply.get("usage") or {}
                self.n_calls += 1
                self.input_tokens += usage.get("input_tokens") or 0
                self.output_tokens += usage.get("output_tokens") or 0
                logger.info(
                    f"{self.provider} usage: in={usage.get('input_tokens')} "
                    f"out={usage.get('output_tokens')}"
                )
                return self._parse_reply(reply, schema)
            except Exception as e:
                code = getattr(e, "response", {}).get("Error", {}).get("Code")
                if code in NON_RETRYABLE_ERRORS:
                    raise
                last_error = e
                logger.warning(
                    f"{self.provider} call failed (attempt {attempt + 1}/{max_retries}): "
                    f"{type(e).__name__}: {e}"
                )
                time.sleep(retry_delay * (2**attempt))
        raise RuntimeError(
            f"No valid {self.provider} response after {max_retries} attempts"
        ) from last_error
