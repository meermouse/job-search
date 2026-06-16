"""
Validates digest_config.yaml on every test run.
Catches structural errors (wrong types, colon-in-unquoted-string parsed as dict, etc.)
before they cause runtime failures in production.
"""
import os
import yaml
import pytest

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "digest_config.yaml")


@pytest.fixture(scope="module")
def config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def test_config_loads_as_valid_yaml(config):
    assert isinstance(config, dict)


def test_config_has_required_top_level_keys(config):
    assert "location" in config
    assert "min_salary" in config


def test_min_salary_is_integer(config):
    assert isinstance(config["min_salary"], int)


def test_location_is_string(config):
    assert isinstance(config["location"], str)


# --- profile block ---

def test_profile_is_dict_when_present(config):
    if "profile" in config:
        assert isinstance(config["profile"], dict)


def test_profile_list_fields_contain_only_strings(config):
    """Catches YAML parsing 'Key: Value' as a dict instead of a string."""
    if "profile" not in config:
        pytest.skip("no profile block")
    profile = config["profile"]
    list_fields = ["skills", "previous_roles", "target_roles", "open_to",
                   "qualifications", "employment_type"]
    for field in list_fields:
        value = profile.get(field)
        if value is None:
            continue
        assert isinstance(value, list), f"profile.{field} must be a list, got {type(value)}"
        for i, item in enumerate(value):
            assert isinstance(item, str), (
                f"profile.{field}[{i}] must be a string, got {type(item).__name__}: {item!r}\n"
                f"Hint: if the value contains a colon, wrap it in quotes in the YAML."
            )


def test_profile_seniority_is_string_when_present(config):
    if "profile" not in config:
        pytest.skip("no profile block")
    seniority = config["profile"].get("seniority")
    if seniority is not None:
        assert isinstance(seniority, str)


# --- static query fallback ---

def test_search_queries_are_strings_when_present(config):
    queries = config.get("search_queries")
    if queries is None:
        pytest.skip("no search_queries block")
    assert isinstance(queries, list)
    for i, q in enumerate(queries):
        assert isinstance(q, str), f"search_queries[{i}] must be a string, got {type(q)}"
