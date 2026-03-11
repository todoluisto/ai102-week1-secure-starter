"""Streamlit UI for the Job Opportunity Scorer.

Run with: streamlit run app.py

Provides:
- Sidebar: Resume PDF upload + profile display
- Main area: Job input via URL (auto-extract) or paste text + classification results
- Bottom: History table of all classified jobs in the session
"""

import json
import logging
import tempfile
from pathlib import Path

import streamlit as st

from src.job_analyzer import ClassificationResult
from src.job_fetcher import JobSearchFilters, fetch_jobs
from src.job_scraper import JobPosting, scrape_job
from src.resume_parser import ResumeProfile, parse_resume
from src.scorer import _get_secrets, score_job

logging.basicConfig(level=logging.INFO)

# ─── Page Config ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Job Opportunity Scorer",
    page_icon="🎯",
    layout="wide",
)

# ─── Session State ────────────────────────────────────────────────
if "profile" not in st.session_state:
    st.session_state.profile = None
if "history" not in st.session_state:
    st.session_state.history = []
if "secrets" not in st.session_state:
    st.session_state.secrets = None
if "search_results" not in st.session_state:
    st.session_state.search_results = []

# ─── Sidebar: Configuration + Resume Upload ──────────────────────
with st.sidebar:
    st.header("Configuration")

    vault_url = st.text_input(
        "Key Vault URI",
        value="https://ai102-kvt2-eus.vault.azure.net/",
    )
    deployment = st.text_input("Deployment Name", value="gpt-4o-mini")
    auth_mode = st.selectbox("Auth Mode", ["key", "identity"])

    if st.button("Connect to Azure"):
        with st.spinner("Retrieving secrets from Key Vault..."):
            try:
                st.session_state.secrets = _get_secrets(vault_url)
                st.success("Connected to Azure services")
            except Exception as e:
                st.error(f"Connection failed: {e}")

    st.divider()
    st.header("Resume Upload")

    uploaded_file = st.file_uploader("Upload your resume (PDF)", type=["pdf"])

    if uploaded_file and st.session_state.secrets:
        if st.session_state.profile is None or st.button("Re-parse Resume"):
            with st.spinner("Parsing resume with Document Intelligence..."):
                try:
                    # Write to temp file for Document Intelligence
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(uploaded_file.getvalue())
                        tmp_path = tmp.name

                    secrets = st.session_state.secrets
                    profile = parse_resume(
                        pdf_path=tmp_path,
                        doc_intel_endpoint=secrets["doc-intel-endpoint"],
                        doc_intel_key=secrets.get("doc-intel-key"),
                        openai_endpoint=secrets["openai-endpoint"],
                        openai_key=secrets.get("openai-key"),
                        deployment_name=deployment,
                        use_identity=(auth_mode == "identity"),
                    )
                    st.session_state.profile = profile
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception as e:
                    st.error(f"Resume parsing failed: {e}")

    if st.session_state.profile:
        profile = st.session_state.profile
        st.success("Resume parsed")
        st.markdown(f"**{profile.summary}**")
        st.markdown(f"**Seniority:** {profile.seniority}")
        st.markdown(f"**Experience:** {profile.experience_years or '?'} years")
        st.markdown(f"**Tech Stack:** {', '.join(profile.tech_stack[:10])}")
        with st.expander("Full Skills"):
            st.write(", ".join(profile.skills))

# ─── Main Area: Job Classification ───────────────────────────────
st.title("Job Opportunity Scorer")

if not st.session_state.secrets:
    st.info("Connect to Azure using the sidebar to get started.")
    st.stop()

if not st.session_state.profile:
    st.info("Upload and parse your resume in the sidebar first.")
    st.stop()


def _display_result(result: ClassificationResult, job_title: str, salary: str | None, company: str | None, source_url: str):
    """Display classification results and save to history."""
    COLORS = {1: "green", 2: "blue", 3: "orange", 4: "violet", 5: "red"}
    color = COLORS.get(result.category_id, "gray")

    st.divider()

    # Job info header
    info_parts = []
    if company:
        info_parts.append(f"**Company:** {company}")
    if salary:
        info_parts.append(f"**Salary:** {salary}")
    if info_parts:
        st.markdown(" | ".join(info_parts))

    # Classification result
    col_badge, col_conf = st.columns([3, 1])
    with col_badge:
        st.markdown(f"### :{color}[{result.category_id}. {result.category_name}]")
    with col_conf:
        st.metric("Confidence", result.confidence.upper())

    st.progress(result.skills_match_pct / 100, text=f"Skills Match: {result.skills_match_pct}%")
    st.markdown(f"**Reasoning:** {result.reasoning}")
    st.markdown(f"**Next Step:** {result.suggested_action}")

    # Save to history
    entry = result.model_dump()
    entry["job_title"] = job_title or "Untitled"
    entry["salary"] = salary or ""
    entry["company"] = company or ""
    entry["source_url"] = source_url or ""
    st.session_state.history.append(entry)


# ─── Tabbed Input: URL, Paste, or Search ─────────────────────────
tab_url, tab_paste, tab_search = st.tabs(["From URL", "Paste Text", "Search Jobs"])

with tab_url:
    job_url = st.text_input(
        "Job Posting URL",
        placeholder="https://boards.greenhouse.io/company/jobs/123456",
    )

    if st.button("Fetch & Classify", type="primary", disabled=not job_url.strip()):
        secrets = st.session_state.secrets
        use_identity = auth_mode == "identity"

        with st.spinner("Fetching job posting..."):
            try:
                posting = scrape_job(
                    url=job_url,
                    primary_endpoint=secrets["openai-endpoint"],
                    primary_key=secrets.get("openai-key"),
                    primary_deployment=deployment,
                    fallback_endpoint=secrets.get("openai-fallback-endpoint"),
                    fallback_key=secrets.get("openai-fallback-key"),
                    fallback_deployment=deployment,
                    use_identity=use_identity,
                )
            except Exception as e:
                st.error(f"Failed to fetch job posting: {e}")
                st.info("Try the 'Paste Text' tab instead if the site requires login or JavaScript.")
                st.stop()

        # Show extracted info for verification
        st.success(f"Extracted: **{posting.job_title}**" + (f" at **{posting.company}**" if posting.company else ""))
        if posting.salary:
            st.info(f"Salary: {posting.salary}")

        with st.expander("Extracted Job Description"):
            st.text(posting.job_description[:2000])

        with st.spinner("Classifying against your profile..."):
            try:
                result = score_job(
                    resume_profile=st.session_state.profile,
                    job_description=posting.job_description,
                    secrets=secrets,
                    deployment_name=deployment,
                    use_identity=use_identity,
                )
                _display_result(result, posting.job_title, posting.salary, posting.company, job_url)
            except Exception as e:
                st.error(f"Classification failed: {e}")

with tab_paste:
    col1, col2 = st.columns([2, 1])

    with col1:
        job_text = st.text_area(
            "Paste Job Description",
            height=300,
            placeholder="Paste the full job description here...",
        )

    with col2:
        paste_url = st.text_input(
            "Source URL (optional)",
            placeholder="https://example.com/job/123",
        )
        paste_title = st.text_input(
            "Job Title (optional)",
            placeholder="Senior Data Engineer",
        )
        paste_salary = st.text_input(
            "Salary (optional)",
            placeholder="$150,000 - $180,000",
        )
        paste_company = st.text_input(
            "Company (optional)",
            placeholder="Acme Corp",
        )

    if st.button("Classify Job", type="primary", disabled=not job_text.strip()):
        with st.spinner("Analyzing job against your profile..."):
            try:
                result = score_job(
                    resume_profile=st.session_state.profile,
                    job_description=job_text,
                    secrets=st.session_state.secrets,
                    deployment_name=deployment,
                    use_identity=(auth_mode == "identity"),
                )
                _display_result(result, paste_title, paste_salary, paste_company, paste_url)
            except Exception as e:
                st.error(f"Classification failed: {e}")

with tab_search:
    col_s1, col_s2 = st.columns([2, 1])

    with col_s1:
        search_company = st.text_input(
            "Company Name *",
            placeholder="Microsoft",
            key="search_company",
        )
        search_keywords = st.text_input(
            "Keywords",
            placeholder="data engineer, ML engineer",
            key="search_keywords",
        )
        search_location = st.text_input(
            "Location",
            placeholder="Remote, New York, NY",
            key="search_location",
        )

    with col_s2:
        search_date = st.selectbox(
            "Date Posted",
            ["week", "today", "3days", "month", "all"],
            key="search_date",
        )
        search_type = st.selectbox(
            "Employment Type",
            [None, "fulltime", "parttime", "contractor", "intern"],
            format_func=lambda x: "Any" if x is None else x.title(),
            key="search_type",
        )
        search_limit = st.number_input(
            "Max Results",
            min_value=1,
            max_value=50,
            value=10,
            key="search_limit",
        )

    if st.button("Search", type="primary", disabled=not search_company.strip()):
        filters = JobSearchFilters(
            company=search_company,
            keywords=search_keywords or None,
            location=search_location or None,
            date_posted=search_date,
            employment_type=search_type,
            max_results=search_limit,
        )
        with st.spinner("Searching for jobs..."):
            try:
                secrets = st.session_state.secrets
                rapidapi_key = secrets.get("rapidapi-key") if secrets else None
                listings = fetch_jobs(filters, api_key=rapidapi_key)
                st.session_state.search_results = listings
                if not listings:
                    st.warning("No jobs found matching your criteria.")
                else:
                    st.success(f"Found {len(listings)} job(s)")
            except Exception as e:
                st.error(f"Search failed: {e}")
                st.session_state.search_results = []

    # Display search results
    if st.session_state.search_results:
        st.subheader(f"Search Results ({len(st.session_state.search_results)})")

        selected = []
        for i, listing in enumerate(st.session_state.search_results):
            col_check, col_info = st.columns([0.5, 9.5])
            with col_check:
                checked = st.checkbox("", key=f"search_sel_{i}")
                if checked:
                    selected.append(i)
            with col_info:
                st.markdown(
                    f"**{listing.title}** — {listing.company} | "
                    f"{listing.location} | {listing.employment_type} | "
                    f"{listing.date_posted[:10] if listing.date_posted else '?'}"
                )

        if st.button(
            f"Classify Selected ({len(selected)})",
            type="primary",
            disabled=len(selected) == 0,
        ):
            secrets = st.session_state.secrets
            use_identity = auth_mode == "identity"

            for idx in selected:
                listing = st.session_state.search_results[idx]
                with st.spinner(f"Classifying: {listing.title}..."):
                    try:
                        result = score_job(
                            resume_profile=st.session_state.profile,
                            job_description=listing.description,
                            secrets=secrets,
                            deployment_name=deployment,
                            use_identity=use_identity,
                        )
                        _display_result(result, listing.title, None, listing.company, listing.url)
                    except Exception as e:
                        st.error(f"Failed to classify '{listing.title}': {e}")

# ─── History Table ────────────────────────────────────────────────
if st.session_state.history:
    st.divider()
    st.subheader(f"Classification History ({len(st.session_state.history)} jobs)")

    display_data = []
    for h in reversed(st.session_state.history):
        display_data.append({
            "Job": h.get("job_title", "—"),
            "Company": h.get("company", "—"),
            "Salary": h.get("salary", "—"),
            "Category": f"{h['category_id']}. {h['category_name']}",
            "Confidence": h["confidence"],
            "Match %": h["skills_match_pct"],
            "Action": h["suggested_action"],
        })

    st.dataframe(display_data, use_container_width=True)

    # Export button
    if st.button("Export History (JSON)"):
        json_str = json.dumps(st.session_state.history, indent=2)
        st.download_button(
            "Download JSON",
            data=json_str,
            file_name="job_classifications.json",
            mime="application/json",
        )
