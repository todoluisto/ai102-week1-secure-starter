"""Job analyzer using Azure OpenAI structured outputs.

AI-102 Exam Mapping:
- Implement generative AI solutions with Azure OpenAI
- Prompt engineering: system prompt structure, structured outputs
- Multi-region fallback for resilience
- Auth: API key (Key Vault) vs DefaultAzureCredential

Classifies a job description against a resume profile into one of
5 categories with confidence, reasoning, and suggested action.
"""

import json
import logging
from pathlib import Path
from typing import Literal

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from jinja2 import Template
from openai import AzureOpenAI
from pydantic import BaseModel, Field

from .categories import format_categories_for_prompt

logger = logging.getLogger(__name__)

API_VERSION = "2024-10-01-preview"

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class ClassificationResult(BaseModel):
    """Structured output schema for job classification."""

    category_id: int = Field(ge=1, le=5)
    category_name: str
    confidence: Literal["high", "medium", "low"]
    reasoning: str
    skills_match_pct: int = Field(ge=0, le=100)
    suggested_action: str


def _build_client(
    endpoint: str,
    key: str | None = None,
    use_identity: bool = False,
) -> AzureOpenAI:
    """Create an AzureOpenAI client with either API key or managed identity."""
    if use_identity:
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        return AzureOpenAI(
            azure_ad_token_provider=token_provider,
            azure_endpoint=endpoint,
            api_version=API_VERSION,
        )
    return AzureOpenAI(
        api_key=key,
        azure_endpoint=endpoint,
        api_version=API_VERSION,
    )


def _load_prompt_template() -> Template:
    """Load the classification prompt template from prompts/classify.txt."""
    template_path = PROMPTS_DIR / "classify.txt"
    return Template(template_path.read_text())


def _call_openai(
    client: AzureOpenAI,
    deployment_name: str,
    system_prompt: str,
    user_prompt: str,
) -> ClassificationResult:
    """Make the classification call and parse the result."""
    try:
        # Try structured outputs first (requires compatible API version)
        response = client.beta.chat.completions.parse(
            model=deployment_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=ClassificationResult,
            temperature=0.2,
        )
        result = response.choices[0].message.parsed
        logger.info(
            "Classification (structured) — tokens: %d input, %d output",
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )
        return result
    except Exception as e:
        logger.warning("Structured outputs failed (%s), falling back to json_object mode", e)

        # Fallback: json_object mode + manual validation
        response = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = json.loads(response.choices[0].message.content)
        logger.info(
            "Classification (json_object) — tokens: %d input, %d output",
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )
        return ClassificationResult(**raw)


def classify(
    resume_profile_text: str,
    job_description: str,
    primary_endpoint: str,
    primary_key: str | None = None,
    primary_deployment: str = "gpt-4o-mini",
    fallback_endpoint: str | None = None,
    fallback_key: str | None = None,
    fallback_deployment: str = "gpt-4o-mini",
    use_identity: bool = False,
) -> ClassificationResult:
    """Classify a job description against a resume profile.

    Tries the primary Azure OpenAI endpoint first. If it fails (rate limit,
    outage, etc.), falls back to the secondary endpoint in a different region.

    Args:
        resume_profile_text: Formatted resume profile text.
        job_description: The job description to classify.
        primary_endpoint: Primary Azure OpenAI endpoint (East US).
        primary_key: Primary API key.
        primary_deployment: Primary model deployment name.
        fallback_endpoint: Fallback Azure OpenAI endpoint (North Central US).
        fallback_key: Fallback API key.
        fallback_deployment: Fallback model deployment name.
        use_identity: Use DefaultAzureCredential instead of API keys.

    Returns:
        ClassificationResult with category, confidence, reasoning, and action.
    """
    template = _load_prompt_template()
    categories_text = format_categories_for_prompt()

    rendered = template.render(
        categories=categories_text,
        resume_profile=resume_profile_text,
        job_description=job_description,
    )

    # Split into system and user parts at the "---" separator
    parts = rendered.split("---", 1)
    system_prompt = parts[0].strip()
    user_prompt = parts[1].strip() if len(parts) > 1 else rendered

    # Try primary endpoint
    try:
        client = _build_client(primary_endpoint, primary_key, use_identity)
        result = _call_openai(client, primary_deployment, system_prompt, user_prompt)
        logger.info("Classification succeeded on primary endpoint")
        return result
    except Exception as e:
        logger.warning("Primary endpoint failed: %s", e)

        if not fallback_endpoint:
            raise

    # Try fallback endpoint
    logger.info("Retrying with fallback endpoint (North Central US)")
    client = _build_client(fallback_endpoint, fallback_key, use_identity)
    result = _call_openai(client, fallback_deployment, system_prompt, user_prompt)
    logger.info("Classification succeeded on fallback endpoint")
    return result
