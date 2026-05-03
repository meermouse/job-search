import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import re as _re


def _min_salary_value(salary_str: str) -> int:
    """Extract the first number from a salary string, or 0 if none found."""
    nums = _re.findall(r"[\d,]+", salary_str)
    if not nums:
        return 0
    return int(nums[0].replace(",", ""))


import cv_parser
import sponsor_filter
from searchers import search_all_streaming

st.set_page_config(page_title="Jie's Job Search", layout="wide")
st.title("Jie's Job Search")
st.caption("Finds UK roles from licensed Skilled Worker visa sponsors only.")

# --- State 1: CV Upload ---
uploaded_file = st.file_uploader("Upload your CV", type=["pdf", "docx", "txt"])

if uploaded_file:
    file_id = f"{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.get("file_id") != file_id:
        st.session_state.file_id = file_id
        st.session_state.pop("cv_analysis", None)
        st.session_state.pop("all_jobs", None)
        st.session_state.pop("filtered_jobs", None)

    if "cv_analysis" not in st.session_state:
        with st.spinner("Analysing CV with Claude..."):
            try:
                text = cv_parser.extract_text(uploaded_file.read(), uploaded_file.name)
                st.session_state.cv_analysis = cv_parser.analyse_cv(text)
            except Exception as e:
                st.error(f"CV analysis failed: {e}")
                st.stop()

if "cv_analysis" in st.session_state:
    analysis = st.session_state.cv_analysis

    with st.expander("Extracted from CV", expanded=True):
        st.write("**Job titles:**", ", ".join(analysis.get("job_titles", [])))
        st.write("**Skills:**", ", ".join(analysis.get("skills", [])))

    queries_text = st.text_area(
        "Search queries (one per line — edit as needed before searching)",
        value="\n".join(analysis.get("search_queries", [])),
        height=120,
    )
    queries = [q.strip() for q in queries_text.splitlines() if q.strip()]

    col1, col2 = st.columns(2)
    with col1:
        location = st.text_input("Location", value="Bristol")
    with col2:
        min_salary = st.number_input("Minimum salary (£)", value=60000, step=5000, min_value=0)

    if st.button("Search", type="primary", disabled=not queries):
        st.session_state.search_params = {
            "queries": queries,
            "location": location,
            "min_salary": int(min_salary),
        }
        st.session_state.pop("all_jobs", None)
        st.session_state.pop("filtered_jobs", None)
        st.rerun()

# --- State 2: Searching ---
if "search_params" in st.session_state and "filtered_jobs" not in st.session_state:
    params = st.session_state.search_params

    with st.spinner("Loading sponsor register..."):
        try:
            sponsor_names = sponsor_filter.load_sponsor_names()
        except RuntimeError as e:
            st.error(str(e))
            st.stop()

    st.subheader("Searching platforms...")
    cols = st.columns(3)
    status_placeholders = {
        "LinkedIn + Indeed": cols[0].empty(),
        "Reed": cols[1].empty(),
        "NHS Jobs": cols[2].empty(),
    }
    for name, ph in status_placeholders.items():
        ph.info(f"⏳ {name}")

    all_jobs: list[dict] = []

    for platform, jobs, error in search_all_streaming(
        params["queries"], params["location"], params["min_salary"]
    ):
        ph = status_placeholders[platform]
        if error:
            ph.warning(f"⚠️ {platform} — error")
        else:
            ph.success(f"✅ {platform} — {len(jobs)} results")
        all_jobs.extend(jobs)

    # Deduplicate by URL
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for job in all_jobs:
        if job["url"] and job["url"] not in seen_urls:
            seen_urls.add(job["url"])
            deduped.append(job)

    st.session_state.all_jobs = deduped
    st.session_state.filtered_jobs = sponsor_filter.filter_jobs(deduped, sponsor_names)
    st.rerun()

# --- State 3: Results ---
if "filtered_jobs" in st.session_state:
    import pandas as pd

    filtered = st.session_state.filtered_jobs
    all_jobs = st.session_state.get("all_jobs", [])

    if filtered:
        st.success(f"{len(filtered)} of {len(all_jobs)} job(s) from licensed Worker-route sponsors")
    else:
        st.warning(
            f"{len(all_jobs)} job(s) found across all platforms — "
            "0 from licensed Worker-route sponsors. "
            "Uncheck 'Licensed sponsors only' below to see all results."
        )

    sponsor_by_url = {j["url"]: j["sponsor_name"] for j in filtered}

    with st.sidebar:
        st.header("Filter results")
        sponsors_only = st.checkbox("Licensed sponsors only", value=True)
        loc_filter = st.text_input("Location contains", value="")
        salary_filter = st.number_input(
            "Minimum salary (£)", value=0, step=5000, min_value=0
        )

    displayed = filtered if sponsors_only else all_jobs
    if loc_filter:
        displayed = [
            j for j in displayed
            if loc_filter.lower() in j.get("location", "").lower()
        ]
    if salary_filter:
        displayed = [
            j for j in displayed
            if _min_salary_value(j.get("salary", "")) >= salary_filter
        ]

    if displayed:
        df = pd.DataFrame(
            [
                {
                    "Title": j["title"],
                    "Company": sponsor_by_url.get(j["url"]) or j.get("company", ""),
                    "Licensed Sponsor": "Yes" if j["url"] in sponsor_by_url else "No",
                    "Location": j["location"],
                    "Salary": j["salary"],
                    "Description": j["description"],
                    "Source": j["source"],
                    "Link": j["url"],
                }
                for j in displayed
            ]
        )
        st.dataframe(
            df,
            column_config={"Link": st.column_config.LinkColumn("Link")},
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No results match the current filters.")

    if st.button("New search"):
        for key in ["cv_analysis", "all_jobs", "filtered_jobs", "search_params", "file_id"]:
            st.session_state.pop(key, None)
        st.rerun()
