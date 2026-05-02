import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

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
