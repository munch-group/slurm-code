---
title: Getting Started
aliases:
  - ../index.html
---

**slurm-code** is a command-line tool for submitting SLURM jobs on [GenomeDK](https://genome.au.dk) and automatically opening VSCode on the allocated compute node. It handles job submission, waits for the node to be ready, and launches a remote VSCode session -- all in one command.

## Installation

::: {.panel-tabset}

## pixi

```bash
pixi workspace channel add munch-group
pixi add slurm-code
```

## conda

```bash
conda install -c munch-group slurm-code
```

## pip

```bash
pip install slurm-code
```

:::

## Prerequisites

- An SSH host alias configured in `~/.ssh/config` for the GenomeDK login node (default alias: `gdk`)
- [VSCode](https://code.visualstudio.com/) with the [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) extension installed

A minimal SSH config entry:

```
Host gdk
    HostName login.genome.au.dk
    User your_username
```

## Quick start

Submit a job and open a remote VSCode window on the allocated node:

```bash
slurm-code submit ~/my-project
```

This will:

1. Submit an `sbatch` job on GenomeDK with default resources (1 CPU, 8 GB memory, 8-hour walltime)
2. Wait for the job to start and the node to accept SSH connections
3. Open VSCode connected to `~/my-project` on the compute node

## Global options

All subcommands accept the `--host` / `-H` option to specify which SSH host alias to use:

```bash
slurm-code -H my-cluster submit ~/project
```

| Option | Default | Description |
|--------|---------|-------------|
| `-H`, `--host` | `gdk` | SSH host alias from `~/.ssh/config` |

## Commands

| Command | Description |
|---------|-------------|
| [`submit`](submit.md) | Submit a SLURM job and open VSCode on the node |
| [`profiles`](profiles.md) | Show available submit profiles |
| [`jobs`](managing-jobs.md#listing-jobs) | List running slurm-code jobs |
| [`cancel`](managing-jobs.md#cancelling-jobs) | Cancel slurm-code jobs |
| [`reconnect`](managing-jobs.md#reconnecting-to-a-job) | Reconnect VSCode to a running job |
