import yaml
import pytest


def test_load_config_returns_expected_keys(tmp_path):
    from digest import load_config

    cfg = {
        "search_queries": ["Data Engineer Bristol"],
        "location": "Bristol",
        "min_salary": 60000,
        "recipient_email": "test@example.com",
    }
    config_file = tmp_path / "digest_config.yaml"
    config_file.write_text(yaml.dump(cfg))

    result = load_config(str(config_file))

    assert result["search_queries"] == ["Data Engineer Bristol"]
    assert result["location"] == "Bristol"
    assert result["min_salary"] == 60000
    assert result["recipient_email"] == "test@example.com"
