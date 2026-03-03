---
title: Submit Profiles
---

Submit profiles let you save frequently used job configurations in a config file and apply them with `--profile <name>`, similar to SSH config host entries.

## Config file location

The config file is located at:

```
~/.slurm-code/config.ini
```

You can override this by setting the `SLURM_CODE_CONFIG` environment variable:

```bash
export SLURM_CODE_CONFIG=~/my-custom-config.ini
```

## Config file format

The file uses INI format (parsed by Python's `configparser`). The special `[DEFAULT]` section provides base values inherited by all named profiles.

```ini
[DEFAULT]
account = my_account
mem_per_cpu = 8g

[standard]
walltime = 08:00:00

[gpu]
partition = gpu
cpus_per_gpu = 4
mem_per_cpu = 16g
walltime = 12:00:00
```

In this example:

- **`[DEFAULT]`** sets `account` and `mem_per_cpu` for all profiles
- **`[standard]`** inherits both defaults and adds a walltime
- **`[gpu]`** inherits `account` from DEFAULT, overrides `mem_per_cpu`, and adds GPU-specific settings

## Valid keys

Profile keys use the same names as the CLI options (with underscores instead of hyphens):

| Key | Corresponding option |
|-----|---------------------|
| `account` | `--account` |
| `cpus_per_task` | `--cpus-per-task` |
| `cpus_per_gpu` | `--cpus-per-gpu` |
| `error` | `--error` |
| `exclude` | `--exclude` |
| `job_name` | `--job-name` |
| `mem` | `--mem` |
| `mem_per_cpu` | `--mem-per-cpu` |
| `mincpus` | `--mincpus` |
| `no_requeue` | `--no-requeue` |
| `nodes` | `--nodes` |
| `nodelist` | `--nodelist` |
| `ntasks` | `--ntasks` |
| `ntasks_per_node` | `--ntasks-per-node` |
| `oom_kill_step` | `--oom-kill-step` |
| `partition` | `--partition` |
| `requeue` | `--requeue` |
| `thread_spec` | `--thread-spec` |
| `use_min_nodes` | `--use-min-nodes` |
| `walltime` | `--walltime` |

Boolean keys (`no_requeue`, `requeue`, `use_min_nodes`) accept `true`/`false`, `yes`/`no`, or `1`/`0`.

## Precedence

When a profile is active, values are resolved in this order (highest priority first):

1. **CLI flags** -- explicitly typed on the command line
2. **Profile values** -- from the named section (including inherited `[DEFAULT]` values)
3. **Click defaults** -- the hardcoded defaults (`--cpus-per-task 1`, `--mem-per-cpu 8g`, etc.)

This means you can always override any profile setting from the command line:

```bash
# Uses gpu profile but overrides the walltime
slurm-code submit -P gpu -t 24:00:00 ~/my-project
```

## Using profiles

Apply a profile with `-P` / `--profile`:

```bash
slurm-code submit -P standard ~/my-project
slurm-code submit -P gpu ~/my-project
```

Without `--profile`, only `[DEFAULT]` values are applied (if the config file exists).

## Viewing profiles

The `profiles` command shows the config file path and all defined profiles with their effective settings:

```bash
slurm-code profiles
```

Example output:

```
Config file: /home/user/.slurm-code/config.ini

[DEFAULT]
  account = my_account
  mem_per_cpu = 8g

[standard]
  walltime = 08:00:00
  account = my_account
  mem_per_cpu = 8g

[gpu]
  partition = gpu
  cpus_per_gpu = 4
  mem_per_cpu = 16g
  walltime = 12:00:00
  account = my_account
```

Named sections show all effective values, including those inherited from `[DEFAULT]`.

## Error handling

Requesting a profile that doesn't exist shows an error with the available profiles:

```
Error: Unknown profile 'fast'. Available: standard, gpu
```

Using an invalid key in the config file also produces a clear error:

```
Error: Invalid key(s) in profile: invalid_key
```
