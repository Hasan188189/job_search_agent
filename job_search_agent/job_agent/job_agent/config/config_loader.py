"""Loads settings.yaml and resolves env var overrides."""

import os
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = Path(__file__).parent / "settings.yaml"
_config = None


def load_config() -> dict:
    global _config
    if _config is not None:
        return _config

    with open(_CONFIG_PATH, "r") as f:
        _config = yaml.safe_load(f)

    # Allow env-var overrides for secrets
    overrides = {
        "ANTHROPIC_API_KEY": ("ai", "anthropic_api_key"),
        "LINKEDIN_EMAIL":    ("platforms", "linkedin", "email"),
        "LINKEDIN_PASSWORD": ("platforms", "linkedin", "password"),
        "INDEED_EMAIL":      ("platforms", "indeed", "email"),
        "INDEED_PASSWORD":   ("platforms", "indeed", "password"),
        "NAUKRI_EMAIL":      ("platforms", "naukri", "email"),
        "NAUKRI_PASSWORD":   ("platforms", "naukri", "password"),
    }
    for env_key, config_path in overrides.items():
        val = os.environ.get(env_key)
        if val:
            node = _config
            for part in config_path[:-1]:
                node = node.setdefault(part, {})
            node[config_path[-1]] = val

    # Resolve resume_path relative to project root
    resume_path = _config.get("profile", {}).get("resume_path", "")
    if resume_path and not Path(resume_path).is_absolute():
        _config["profile"]["resume_path"] = str(PROJECT_ROOT / resume_path)

    # Resolve db_path relative to project root
    db_path = _config.get("tracker", {}).get("db_path", "")
    if db_path and not Path(db_path).is_absolute():
        _config["tracker"]["db_path"] = str(PROJECT_ROOT / db_path)

    return _config
