import os
import pytest
from rapidfuzz import fuzz
from sponsor_filter import load_sponsor_names, filter_jobs

REAL_CACHE = os.path.join(os.path.dirname(__file__), "..", "sponsor_cache.csv")


# --- token_set_ratio assumption tests ---
# These document and verify that the scorer we use handles the common pattern
# of "trading name" vs "full legal name with suffix" without needing the real CSV.

@pytest.mark.parametrize("query,legal_name", [
    ("Liverpool Football Club", "The Liverpool Football Club and Athletic Grounds Limited"),
    ("John Lewis", "John Lewis Partnership PLC"),
    ("KPMG", "KPMG LLP"),
    ("Deloitte", "Deloitte LLP"),
    ("Rolls-Royce", "Rolls-Royce PLC"),
    ("Manchester City", "Manchester City Football Club Limited"),
    ("AECOM", "AECOM LIMITED"),
])
def test_token_set_ratio_passes_threshold_for_common_vs_legal_name(query, legal_name):
    """Common trading names are a token-subset of their legal name — score must reach 85%."""
    assert fuzz.token_set_ratio(query, legal_name) >= 85

FIXTURE_CSV = os.path.join(os.path.dirname(__file__), "fixtures", "sponsors.csv")


def test_load_sponsor_names_filters_worker_route_only(mocker):
    with open(FIXTURE_CSV, encoding="utf-8") as f:
        csv_text = f.read()
    mock_response = mocker.MagicMock()
    mock_response.text = csv_text
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("sponsor_filter.requests.get", return_value=mock_response)
    mocker.patch("builtins.open", mocker.mock_open())

    names = load_sponsor_names("https://example.com/sponsors.csv", cache_path="/tmp/test_cache.csv")

    assert "NHS Bristol Trust" in names
    assert "Acme Technologies Ltd" in names
    assert "Big Data Corp" in names
    assert "Temp Solutions UK" not in names  # Temporary Worker route excluded
    assert len(names) == 4


def test_load_sponsor_names_falls_back_to_cache_on_network_error(mocker, tmp_path):
    with open(FIXTURE_CSV, encoding="utf-8") as f:
        csv_text = f.read()
    cache_file = tmp_path / "sponsors_cache.csv"
    cache_file.write_text(csv_text, encoding="utf-8")
    mocker.patch("sponsor_filter.requests.get", side_effect=Exception("Network error"))

    names = load_sponsor_names("https://example.com/sponsors.csv", cache_path=str(cache_file))

    assert "NHS Bristol Trust" in names
    assert "Temp Solutions UK" not in names


def test_load_sponsor_names_raises_when_no_cache(mocker, tmp_path):
    mocker.patch("sponsor_filter.requests.get", side_effect=Exception("Network error"))
    missing_cache = str(tmp_path / "nonexistent.csv")

    with pytest.raises(RuntimeError, match="Failed to download sponsor CSV"):
        load_sponsor_names("https://example.com/sponsors.csv", cache_path=missing_cache)


from sponsor_filter import filter_jobs

SPONSOR_NAMES = ["NHS Bristol Trust", "Acme Technologies Ltd", "Big Data Corp"]

SAMPLE_JOBS = [
    {
        "title": "Data Engineer",
        "company": "Acme Technologies",  # close but not exact
        "location": "London",
        "salary": "£65,000",
        "description": "Great role",
        "url": "https://example.com/1",
        "source": "LinkedIn",
    },
    {
        "title": "Nurse",
        "company": "NHS Bristol Trust",  # exact match
        "location": "Bristol",
        "salary": "£35,000",
        "description": "Ward nurse",
        "url": "https://example.com/2",
        "source": "NHS Jobs",
    },
    {
        "title": "Barista",
        "company": "Coffee Shop Ltd",  # no match
        "location": "Bristol",
        "salary": "£22,000",
        "description": "Coffee",
        "url": "https://example.com/3",
        "source": "Reed",
    },
]


def test_filter_jobs_passes_fuzzy_match():
    result = filter_jobs(SAMPLE_JOBS, SPONSOR_NAMES)
    urls = [j["url"] for j in result]
    assert "https://example.com/1" in urls  # Acme Technologies ~= Acme Technologies Ltd


def test_filter_jobs_passes_exact_match():
    result = filter_jobs(SAMPLE_JOBS, SPONSOR_NAMES)
    urls = [j["url"] for j in result]
    assert "https://example.com/2" in urls


def test_filter_jobs_blocks_non_sponsor():
    result = filter_jobs(SAMPLE_JOBS, SPONSOR_NAMES)
    urls = [j["url"] for j in result]
    assert "https://example.com/3" not in urls  # Coffee Shop Ltd not a sponsor


def test_filter_jobs_adds_sponsor_name():
    result = filter_jobs(SAMPLE_JOBS, SPONSOR_NAMES)
    acme_job = next(j for j in result if j["url"] == "https://example.com/1")
    assert acme_job["sponsor_name"] == "Acme Technologies Ltd"


def test_filter_jobs_empty_input():
    assert filter_jobs([], SPONSOR_NAMES) == []


def test_filter_jobs_respects_threshold():
    # "Xyz Corp" won't match anything at 85% threshold
    jobs = [{
        "title": "CEO",
        "company": "Xyz Corp",
        "location": "London",
        "salary": "",
        "description": "",
        "url": "https://example.com/4",
        "source": "Reed",
    }]
    assert filter_jobs(jobs, SPONSOR_NAMES, threshold=85) == []


def _make_nhs_job(url, company):
    return {
        "title": "Director",
        "company": company,
        "location": "Wales",
        "salary": "£75,000",
        "description": "",
        "url": url,
        "source": "NHS Jobs",
    }


def test_filter_jobs_bypasses_fuzzy_match_for_nhs_in_name():
    # "NHS" in the company name should pass without needing to be in the sponsor list
    job = _make_nhs_job("https://example.com/nhs1", "Cwm Taf Morgannwg University NHS Trust")
    result = filter_jobs([job], sponsor_names=[], threshold=85)
    assert len(result) == 1
    assert result[0]["sponsor_name"] == "Cwm Taf Morgannwg University NHS Trust"


def test_filter_jobs_bypasses_fuzzy_match_for_public_health_wales():
    job = _make_nhs_job("https://example.com/phw1", "Public Health Wales")
    result = filter_jobs([job], sponsor_names=[], threshold=85)
    assert len(result) == 1


def test_filter_jobs_bypasses_fuzzy_match_for_health_board():
    # Welsh and Scottish NHS bodies use "Health Board" rather than "NHS Trust"
    job = _make_nhs_job("https://example.com/hb1", "Aneurin Bevan University Health Board")
    result = filter_jobs([job], sponsor_names=[], threshold=85)
    assert len(result) == 1


def test_filter_jobs_bypasses_fuzzy_match_for_foundation_trust():
    job = _make_nhs_job("https://example.com/ft1", "Bristol Royal Infirmary Foundation Trust")
    result = filter_jobs([job], sponsor_names=[], threshold=85)
    assert len(result) == 1


def test_filter_jobs_non_nhs_still_requires_fuzzy_match():
    # A private company without NHS terms must still match the register
    job = _make_nhs_job("https://example.com/priv1", "Priory Group")
    result = filter_jobs([job], sponsor_names=[], threshold=85)
    assert result == []


# --- integration tests against the real sponsor_cache.csv ---

def _make_job_for(company, url="https://example.com/x"):
    return {
        "title": "Project Manager",
        "company": company,
        "location": "London",
        "salary": "£70,000",
        "description": "",
        "url": url,
        "source": "LinkedIn",
    }


@pytest.mark.skipif(not os.path.exists(REAL_CACHE), reason="sponsor_cache.csv not present")
def test_aecom_passes_sponsor_filter(mocker):
    """AECOM is on the register as 'AECOM LIMITED' — short name vs suffixed name must still match."""
    mocker.patch("sponsor_filter.requests.get", side_effect=Exception("force cache"))
    names = load_sponsor_names(cache_path=REAL_CACHE)
    result = filter_jobs([_make_job_for("AECOM")], names)
    assert len(result) == 1, "AECOM should pass the sponsor filter"


@pytest.mark.skipif(not os.path.exists(REAL_CACHE), reason="sponsor_cache.csv not present")
def test_equans_fails_sponsor_filter(mocker):
    """Equans is not on the register and should be filtered out."""
    mocker.patch("sponsor_filter.requests.get", side_effect=Exception("force cache"))
    names = load_sponsor_names(cache_path=REAL_CACHE)
    result = filter_jobs([_make_job_for("Equans")], names)
    assert len(result) == 0, "Equans is not a registered sponsor and should be rejected"
