import html
import streamlit as st
import dismiss_store

st.set_page_config(page_title="Dismiss Jobs", layout="wide")

today_data = dismiss_store.load_today_jobs()
if today_data is None:
    st.title("Jie's Job Digest — Dismiss Jobs")
    st.info("No jobs to review yet — check back after today's digest has run.")
    st.stop()

date_str = today_data.get("date", "")
st.title(f"Jie's Job Digest — {date_str}")

dismissed_set = dismiss_store.load_dismissed_urls()

total_jobs = sum(
    len(today_data.get(k, []))
    for k in ("strong", "worth_a_look", "near_misses")
)
dismissed_count = sum(
    1
    for k in ("strong", "worth_a_look", "near_misses")
    for j in today_data.get(k, [])
    if j.get("url") in dismissed_set
)
if dismissed_count:
    st.caption(f"{dismissed_count} of {total_jobs} job(s) dismissed")


def _render_section(section_key: str, heading: str, jobs: list[dict]) -> None:
    if not jobs:
        return
    st.subheader(heading)
    header_cols = st.columns([1, 4, 3, 2, 2, 1, 5])
    for label, col in zip(
        ["Dismiss", "Job Title", "Company", "Location", "Salary", "Source", "Why"],
        header_cols,
    ):
        col.markdown(f"**{label}**")

    for idx, job in enumerate(jobs):
        url = job.get("url", "")
        is_dismissed = url in dismissed_set
        opacity = "0.4" if is_dismissed else "1.0"

        row_cols = st.columns([1, 4, 3, 2, 2, 1, 5])

        with row_cols[0]:
            btn_label = "Restore" if is_dismissed else "Dismiss"
            if st.button(btn_label, key=f"{section_key}_{idx}"):
                if is_dismissed:
                    dismissed_set.discard(url)
                else:
                    dismissed_set.add(url)
                try:
                    dismiss_store.save_dismissed_urls(dismissed_set)
                except Exception as e:
                    st.error(f"Could not save: {e}")
                st.rerun()

        title = job.get("title", "")
        title_html = (
            f"<a href='{html.escape(url)}'>{html.escape(title)}</a>"
            if url
            else html.escape(title)
        )
        company = job.get("sponsor_name") or job.get("company", "")
        cells = [
            title_html,
            html.escape(company),
            html.escape(job.get("location", "")),
            html.escape(job.get("salary", "")),
            html.escape(job.get("source", "")),
            html.escape(job.get("reasoning", "")),
        ]
        for cell_html, col in zip(cells, row_cols[1:]):
            col.markdown(
                f"<div style='opacity:{opacity}'>{cell_html}</div>",
                unsafe_allow_html=True,
            )


_render_section("strong", "Strong matches", today_data.get("strong", []))
_render_section("worth", "Worth a look", today_data.get("worth_a_look", []))
_render_section("near", "Near misses", today_data.get("near_misses", []))
