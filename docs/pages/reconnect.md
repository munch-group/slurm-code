---
title: Reconnecting to Jobs
---

slurm-code provides commands to list, cancel, and reconnect to jobs that were submitted through `slurm-code submit`. These commands identify managed jobs by their `sc-` name prefix.

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
