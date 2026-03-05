"""Profile configuration for slurm-code."""

import configparser
import os
from pathlib import Path

import click

VALID_PROFILE_KEYS = frozenset(
    {
        "account",
        "cpus_per_task",
        "error",
        "job_name",
        "ntasks",
        "no_requeue",
        "ntasks_per_node",
        "nodes",
        "oom_kill_step",
        "partition",
        "pixi",
        "requeue",
        "thread_spec",
        "walltime",
        "use_min_nodes",
        "mem",
        "mincpus",
        "nodelist",
        "exclude",
        "mem_per_cpu",
        "cpus_per_gpu",
    }
)

BOOL_KEYS = frozenset({"no_requeue", "pixi", "requeue", "use_min_nodes"})


def get_config_path() -> Path:
    """Return the config file path.

    Checks SLURM_CODE_CONFIG env var first, falls back to
    ~/.slurm-code/config.ini.
    """
    env = os.environ.get("SLURM_CODE_CONFIG")
    if env:
        return Path(env)
    return Path(click.get_app_dir("slurm-code", force_posix=True)) / "config.ini"


def load_config() -> configparser.ConfigParser:
    """Load config from disk. Returns empty parser if file doesn't exist."""
    config = configparser.ConfigParser()
    path = get_config_path()
    if path.exists():
        config.read(path)
    return config


def get_profile(
    config: configparser.ConfigParser, profile_name: str | None
) -> dict[str, str]:
    """Return profile values as a dict.

    If profile_name is None, returns DEFAULT section values only.
    Raises click.UsageError for unknown profiles or invalid keys.
    """
    if profile_name is None:
        section = dict(config.defaults())
    else:
        if not config.has_section(profile_name):
            available = config.sections()
            if available:
                names = ", ".join(available)
                msg = f"Unknown profile '{profile_name}'. Available: {names}"
            else:
                msg = f"Unknown profile '{profile_name}'. No profiles defined in {get_config_path()}"
            raise click.UsageError(msg)
        section = dict(config[profile_name])

    invalid = set(section) - VALID_PROFILE_KEYS
    if invalid:
        raise click.UsageError(
            f"Invalid key(s) in profile: {', '.join(sorted(invalid))}"
        )

    return section


def coerce_profile_value(key: str, value: str) -> str | bool:
    """Coerce a profile string value to the appropriate Python type.

    Bool keys are converted from "true"/"false" strings. All others pass through.
    """
    if key in BOOL_KEYS:
        return value.lower() in ("true", "yes", "1")
    return value
