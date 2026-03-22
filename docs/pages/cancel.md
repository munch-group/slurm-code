---
title: Cancel Jobs
---

slurm-code provides commands to list, cancel, and reconnect to jobs that were submitted through `slurm-code submit`. These commands identify managed jobs by their `sc-` name prefix.

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
