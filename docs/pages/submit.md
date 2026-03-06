---
title: Submitting Jobs
---

The `submit` command creates a SLURM job, waits for a node to be allocated and ready, then opens VSCode connected to that node.

## Usage

```bash
slurm-code submit [OPTIONS] [DIRECTORY]
```

`DIRECTORY` is an optional path on the remote host to open in VSCode. Relative paths are resolved relative to `$HOME`. If omitted, VSCode opens the welcome screen on the allocated node.

## Examples

Submit with default settings and open a project directory:

```bash
slurm-code submit ~/my-project
```

Request more memory and a longer walltime:

```bash
slurm-code submit -m 16g -t 12:00:00 ~/my-project
```

Submit to the GPU partition with a named profile:

```bash
slurm-code submit -P gpu ~/my-project
```

Override a profile's walltime from the command line:

```bash
slurm-code submit -P gpu -t 24:00:00 ~/my-project
```

Submit without opening a specific directory:

```bash
slurm-code submit -A my_account
```

## Options

### Resource allocation

| Option | Default | Description |
|--------|---------|-------------|
| `-A`, `--account` | | Charge job to specified account |
| `-c`, `--cpus-per-task` | `1` | CPUs per task |
| `-n`, `--ntasks` | `1` | Number of tasks |
| `-N`, `--nodes` | | Number of nodes (`N` or `min-max`) |
| `--ntasks-per-node` | | Tasks per node |
| `--mincpus` | | Minimum logical processors per node |
| `--cpus-per-gpu` | | CPUs per allocated GPU |

### Memory

| Option | Default | Description |
|--------|---------|-------------|
| `-m`, `--mem-per-cpu` | `8g` | Memory per allocated CPU |
| `--mem` | | Minimum total real memory (e.g. `4g`) |

### Time and scheduling

| Option | Default | Description |
|--------|---------|-------------|
| `-t`, `--walltime` | `08:00:00` | Time limit (e.g. `08:00:00`) |
| `-p`, `--partition` | | Partition requested |

### Job identity

| Option | Default | Description |
|--------|---------|-------------|
| `-J`, `--job-name` | `sc-<dirname>` | Job name (auto-derived from directory if not set) |
| `-e`, `--error` | | File for batch script's standard error |

### Node selection

| Option | Description |
|--------|-------------|
| `-w`, `--nodelist` | Request specific hosts |
| `-x`, `--exclude` | Exclude specific hosts |
| `--use-min-nodes` | Prefer smaller node count |

### Job behaviour

| Option | Description |
|--------|-------------|
| `--requeue` | Permit the job to be requeued |
| `--no-requeue` | Do not requeue the job |
| `--oom-kill-step` | OOMKillStep behaviour (`0` or `1`) |
| `--thread-spec` | Count of reserved threads |

### Environment

| Option | Description |
|--------|-------------|
| `--pixi` | Activate the [pixi](https://pixi.sh) environment from DIRECTORY on the allocated node |

When `--pixi` is used, slurm-code runs `pixi shell-hook` in the project directory and writes the activation commands to `<DIRECTORY>/.slurm-code-pixi-env.sh`. On first use, you will be prompted to add a source line to `~/.bashrc` so that VSCode integrated terminals automatically activate the pixi environment. The activation script is overwritten on each `--pixi` submit, so it always reflects the current environment. The bashrc hook sources `.slurm-code-pixi-env.sh` relative to the current working directory, so it only activates when the shell starts in the project directory (as VSCode integrated terminals do). Regular SSH login shells start in `~` and are unaffected.

You can also set `pixi = true` in a [submit profile](profiles.md) to always activate pixi for that profile.

### Profiles

| Option | Description |
|--------|-------------|
| `-P`, `--profile` | Apply a named submit profile from the config file |

See [Submit Profiles](profiles.md) for details on setting up and using profiles.

## What happens when you submit

1. The remote directory is verified on the host (if specified)
2. An `sbatch` command is built from CLI flags, profile values, and defaults
3. The job is submitted via SSH
4. slurm-code polls `squeue` until the job enters RUNNING state
5. SSH connectivity to the allocated node is verified
6. If `--pixi` is set, the pixi environment is activated and the bashrc hook is configured
7. VSCode opens with a remote connection to the node

## Job naming

Jobs are automatically named `sc-<dirname>` based on the directory basename. For example, submitting `~/projects/my-analysis` creates a job named `sc-my-analysis`. If no directory is given, the name is `sc-<timestamp>`. You can override this with `--job-name`.

The `sc-` prefix is how slurm-code identifies its own jobs for the `jobs`, `cancel`, and `connect` commands.
