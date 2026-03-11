"""Resume parser using Azure AI Document Intelligence.

AI-102 Exam Mapping:
- Implement document intelligence solutions (prebuilt-layout model)
- Authenticate with both API key and DefaultAzureCredential
- Use Key Vault for secret management

Flow: PDF file → Document Intelligence (prebuilt-layout) → raw text
     → Azure OpenAI structuring call → ResumeProfile dataclass
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI

logger = logging.getLogger(__name__)

PROFILE_STRUCTURING_PROMPT = """\
You are a resume parser. Given raw text extracted from a resume PDF, produce a structured profile.

Extract the following fields:
- skills: list of technical and professional skills mentioned
- experience_years: estimated total years of professional experience (integer or null)
- seniority: one of "junior", "mid", "senior", "staff", "principal" based on experience and titles
- tech_stack: list of programming languages, frameworks, platforms, and tools
- education: list of degrees and certifications
- summary: 2-3 sentence professional summary

Respond with valid JSON matching this schema:
{
  "skills": ["skill1", "skill2"],
  "experience_years": 8,
  "seniority": "senior",
  "tech_stack": ["Python", "Azure", "Spark"],
  "education": ["B.S. Computer Science"],
  "summary": "Senior data engineer with 8 years..."
}

Resume text:
"""


@dataclass
class ResumeProfile:
    raw_text: str
    skills: list[str]
    experience_years: int | None
    seniority: str
    tech_stack: list[str]
    education: list[str]
    summary: str

    def to_prompt_text(self) -> str:
        """Format profile for inclusion in classification prompt."""
        return (
            f"Summary: {self.summary}\n"
            f"Seniority: {self.seniority}\n"
            f"Experience: {self.experience_years or 'unknown'} years\n"
            f"Tech Stack: {', '.join(self.tech_stack)}\n"
            f"Skills: {', '.join(self.skills)}\n"
            f"Education: {', '.join(self.education)}"
        )


def extract_text_from_pdf(
    pdf_path: str,
    endpoint: str,
    key: str | None = None,
    use_identity: bool = False,
) -> str:
    """Extract text from a PDF using Azure Document Intelligence prebuilt-layout.

    Args:
        pdf_path: Path to the PDF file.
        endpoint: Document Intelligence endpoint URL.
        key: API key (used when use_identity=False).
        use_identity: If True, use DefaultAzureCredential instead of API key.

    Returns:
        Extracted text content from the PDF.
    """
    if use_identity:
        credential = DefaultAzureCredential()
    else:
        credential = AzureKeyCredential(key)

    client = DocumentIntelligenceClient(endpoint=endpoint, credential=credential)

    with open(pdf_path, "rb") as f:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            body=f,
            content_type="application/octet-stream",
        )

    result = poller.result()

    # Concatenate all page content in reading order
    text_parts = []
    if result.content:
        text_parts.append(result.content)

    extracted = "\n".join(text_parts) if text_parts else ""
    logger.info("Extracted %d characters from %s", len(extracted), pdf_path)
    return extracted


def structure_profile(
    raw_text: str,
    openai_endpoint: str,
    openai_key: str | None = None,
    deployment_name: str = "gpt-4o-mini",
    use_identity: bool = False,
) -> ResumeProfile:
    """Use Azure OpenAI to structure raw resume text into a ResumeProfile.

    Args:
        raw_text: Raw text extracted from the resume PDF.
        openai_endpoint: Azure OpenAI endpoint URL.
        openai_key: API key (used when use_identity=False).
        deployment_name: Name of the deployed model.
        use_identity: If True, use DefaultAzureCredential.

    Returns:
        Structured ResumeProfile.
    """
    api_version = "2024-10-01-preview"

    if use_identity:
        from azure.identity import get_bearer_token_provider

        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        client = AzureOpenAI(
            azure_ad_token_provider=token_provider,
            azure_endpoint=openai_endpoint,
            api_version=api_version,
        )
    else:
        client = AzureOpenAI(
            api_key=openai_key,
            azure_endpoint=openai_endpoint,
            api_version=api_version,
        )

    response = client.chat.completions.create(
        model=deployment_name,
        messages=[
            {"role": "system", "content": "You are a precise resume parser. Output valid JSON only."},
            {"role": "user", "content": PROFILE_STRUCTURING_PROMPT + raw_text},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    parsed = json.loads(response.choices[0].message.content)
    logger.info(
        "Structured profile — tokens: %d input, %d output",
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
    )

    return ResumeProfile(
        raw_text=raw_text,
        skills=parsed.get("skills", []),
        experience_years=parsed.get("experience_years"),
        seniority=parsed.get("seniority", "unknown"),
        tech_stack=parsed.get("tech_stack", []),
        education=parsed.get("education", []),
        summary=parsed.get("summary", ""),
    )


def parse_resume(
    pdf_path: str,
    doc_intel_endpoint: str,
    doc_intel_key: str | None,
    openai_endpoint: str,
    openai_key: str | None,
    deployment_name: str = "gpt-4o-mini",
    use_identity: bool = False,
    cache_dir: str | None = None,
) -> ResumeProfile:
    """Full pipeline: PDF → Document Intelligence → OpenAI → ResumeProfile.

    Caches the parsed profile to a JSON file to avoid re-parsing on every run.

    Args:
        pdf_path: Path to the resume PDF.
        doc_intel_endpoint: Document Intelligence endpoint.
        doc_intel_key: Document Intelligence API key.
        openai_endpoint: Azure OpenAI endpoint.
        openai_key: Azure OpenAI API key.
        deployment_name: Model deployment name.
        use_identity: Use DefaultAzureCredential for all services.
        cache_dir: Directory to cache parsed profiles. If None, no caching.

    Returns:
        Parsed and structured ResumeProfile.
    """
    # Check cache
    if cache_dir:
        cache_path = Path(cache_dir) / f"{Path(pdf_path).stem}_profile.json"
        if cache_path.exists():
            logger.info("Loading cached profile from %s", cache_path)
            data = json.loads(cache_path.read_text())
            return ResumeProfile(**data)

    # Step 1: Extract text via Document Intelligence
    raw_text = extract_text_from_pdf(
        pdf_path=pdf_path,
        endpoint=doc_intel_endpoint,
        key=doc_intel_key,
        use_identity=use_identity,
    )

    # Step 2: Structure via Azure OpenAI
    profile = structure_profile(
        raw_text=raw_text,
        openai_endpoint=openai_endpoint,
        openai_key=openai_key,
        deployment_name=deployment_name,
        use_identity=use_identity,
    )

    # Cache result
    if cache_dir:
        cache_path = Path(cache_dir) / f"{Path(pdf_path).stem}_profile.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(asdict(profile), indent=2))
        logger.info("Cached profile to %s", cache_path)

    return profile
