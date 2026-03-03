---
title: Managing Jobs
---

slurm-code provides commands to list, cancel, and reconnect to jobs that were submitted through `slurm-code submit`. These commands identify managed jobs by their `sc-` name prefix.

## Listing jobs {#listing-jobs}

The `jobs` command shows your running slurm-code jobs:

```bash
slurm-code jobs
```

Example output:

```
     JOBID  NAME                            PARTITION     REQMEM    CPUS    TIMELIMIT     ELAPSED       STATE
----------------------------------------------------------------------------------------------------------
   1234567  sc-my-project                   normal        8Gn       1       08:00:00      01:23:45      RUNNING
   1234568  sc-analysis                     normal        16Gn      4       12:00:00      00:45:12      RUNNING
```

### Options

| Option | Description |
|--------|-------------|
| `--all-states` | Include PENDING jobs (default: RUNNING only) |

To also see pending jobs:

```bash
slurm-code jobs --all-states
```

## Cancelling jobs {#cancelling-jobs}

The `cancel` command cancels slurm-code managed jobs.

### Cancel by job ID

```bash
slurm-code cancel 1234567
```

### Cancel by name

You can use the directory basename (without the `sc-` prefix):

```bash
slurm-code cancel my-project
```

Or the full job name:

```bash
slurm-code cancel sc-my-project
```

### Cancel all jobs

```bash
slurm-code cancel --all
```

### Options

| Argument/Option | Description |
|-----------------|-------------|
| `JOB_ID_OR_NAME` | A job ID (numeric) or job name to cancel |
| `--all` | Cancel all slurm-code managed jobs |

## Reconnecting to a job {#reconnecting-to-a-job}

If VSCode disconnects or you close the window, use `reconnect` to reopen it on the same node:

```bash
slurm-code reconnect ~/my-project
```

This finds the running job that matches the directory name and opens VSCode on its allocated node. Relative paths are resolved relative to `$HOME`.

If multiple jobs match the directory name, you'll be prompted to select one:

```
Multiple matching jobs found:
  [1] 1234567  01:23:45  RUNNING
  [2] 1234568  00:45:12  RUNNING
Select job number:
```

### Usage

```bash
slurm-code reconnect DIRECTORY
```

| Argument | Description |
|----------|-------------|
| `DIRECTORY` | Path on the remote host (used to match the job name) |
