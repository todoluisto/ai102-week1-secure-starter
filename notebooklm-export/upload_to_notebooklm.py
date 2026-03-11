"""Upload codebase summary to NotebookLM and generate an infographic.

Prerequisites:
    pip install "notebooklm-py[browser]"
    playwright install chromium
    notebooklm login

Usage:
    python3.10 upload_to_notebooklm.py
    python3.10 upload_to_notebooklm.py --infographic
"""

import argparse
import asyncio
from pathlib import Path

from notebooklm import NotebookLMClient, InfographicDetail, InfographicOrientation


NOTEBOOK_TITLE = "AI-102 SANDBOX — Codebase Overview"

# Sources to upload (relative to this script's directory)
SOURCES = [
    "codebase-summary.md",
    "../README.md",
    "../week2-job-scorer/README.md",
    "../week2-job-scorer/architecture.md",
]

# Key source code files to include as text sources
CODE_SOURCES = [
    ("scorer.py — CLI orchestrator", "../week2-job-scorer/src/scorer.py"),
    ("job_analyzer.py — Classification engine", "../week2-job-scorer/src/job_analyzer.py"),
    ("resume_parser.py — Document Intelligence pipeline", "../week2-job-scorer/src/resume_parser.py"),
    ("categories.py — 5-bucket schema", "../week2-job-scorer/src/categories.py"),
    ("classify.txt — Jinja2 prompt template", "../week2-job-scorer/prompts/classify.txt"),
    ("app.py — Streamlit UI", "../week2-job-scorer/app.py"),
]


async def main(generate_infographic: bool = False):
    script_dir = Path(__file__).parent

    async with await NotebookLMClient.from_storage() as client:
        # 1. Create notebook
        print(f"Creating notebook: {NOTEBOOK_TITLE}")
        nb = await client.notebooks.create(NOTEBOOK_TITLE)
        print(f"  Notebook ID: {nb.id}")

        source_ids = []

        # 2. Upload markdown/doc sources
        for source_rel in SOURCES:
            source_path = (script_dir / source_rel).resolve()
            if not source_path.exists():
                print(f"  SKIP (not found): {source_rel}")
                continue
            print(f"  Uploading: {source_rel}")
            src = await client.sources.add_file(nb.id, str(source_path), wait=True)
            source_ids.append(src.id)
            print(f"    Source ID: {src.id}")

        # 3. Upload code files as text sources
        for label, code_rel in CODE_SOURCES:
            code_path = (script_dir / code_rel).resolve()
            if not code_path.exists():
                print(f"  SKIP (not found): {code_rel}")
                continue
            content = code_path.read_text()
            text_source = f"# Source File: {label}\n# Path: {code_rel}\n\n```python\n{content}\n```"
            print(f"  Uploading code: {label}")
            src = await client.sources.add_text(nb.id, label, text_source, wait=True)
            source_ids.append(src.id)
            print(f"    Source ID: {src.id}")

        print(f"\nNotebook ready with {len(source_ids)} sources!")

        # 4. Generate infographic
        if generate_infographic:
            print("\nGenerating infographic...")
            instructions = (
                "Create a visual infographic of this AI-102 study project. "
                "Show the architecture: resume PDF flows through Azure Document Intelligence, "
                "then Azure OpenAI structures it into a profile. Job descriptions are classified "
                "into 5 categories (Strong Fit, Stretch Role, Interesting, Needs Research, Not Relevant). "
                "Highlight the multi-region failover (East US primary, North Central US fallback), "
                "Key Vault for secrets, Log Analytics for monitoring, and the dual auth paths "
                "(API key vs managed identity). Show how it maps to AI-102 exam objectives."
            )
            status = await client.artifacts.generate_infographic(
                nb.id,
                source_ids=source_ids,
                instructions=instructions,
                orientation=InfographicOrientation.PORTRAIT,
                detail_level=InfographicDetail.DETAILED,
            )
            print(f"  Generation status: {status}")

            if status.task_id:
                print("  Waiting for infographic to complete...")
                final = await client.artifacts.wait_for_completion(
                    nb.id, status.task_id, timeout=300.0
                )
                print(f"  Final status: {final}")

                # Download
                output_path = str(script_dir / "ai102-codebase-infographic.png")
                await client.artifacts.download_infographic(nb.id, output_path)
                print(f"  Infographic saved to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload codebase to NotebookLM")
    parser.add_argument(
        "--infographic", action="store_true", help="Generate infographic"
    )
    args = parser.parse_args()

    asyncio.run(main(generate_infographic=args.infographic))
