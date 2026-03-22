---
title: Listing Jobs
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
