"""Core business logic for slurm-code CLI."""

import os
import re
import subprocess
import time
from datetime import datetime

JOB_NAME_PREFIX = "sc-"
# Also match jobs created with the old prefix
_KNOWN_PREFIXES = ("sc-", "slurm-code-")


def run_command(command):
    """Run a shell command and return the output.

    Raises RuntimeError on non-zero exit code.
    """
    result = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def run_remote(command, host="gdk"):
    """Run a command via SSH on the given host."""
    return run_command(f"ssh {host} '{command}'")


def check_remote_directory(directory, host="gdk"):
    """Check if a directory exists on the remote server and return its expanded path.

    Returns the expanded absolute path if it exists, None otherwise.
    """
    result = subprocess.run(
        f"ssh {host} 'realpath {directory}'",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        return None

    expanded_path = result.stdout.strip()

    test_result = subprocess.run(
        f"ssh {host} 'test -d {expanded_path}'",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if test_result.returncode == 0:
        return expanded_path
    return None


def derive_job_name(directory=None):
    """Derive a job name from a directory path, or from a timestamp if no directory.

    E.g. ~/projects/my-analysis -> sc-my-analysis
         None -> sc-20260302-143022
    """
    if directory:
        basename = os.path.basename(directory.rstrip("/"))
        return f"{JOB_NAME_PREFIX}{basename}"
    return f"{JOB_NAME_PREFIX}{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def build_sbatch_command(params):
    """Build sbatch command from a parameter dict.

    The dict may contain keys matching sbatch long-option names (underscores OK).
    Sets --chdir to the resolved directory if provided. Derives the job name from
    the directory basename (or a timestamp if no directory) unless an explicit
    job_name is provided.
    """
    cmd_parts = ["sbatch"]

    directory = params.get("directory")
    if directory:
        cmd_parts.append(f"--chdir={directory}")

    job_name = params.get("job_name") or derive_job_name(directory)
    cmd_parts.append(f"--job-name={job_name}")

    option_map = {
        "account": "--account",
        "cpus_per_task": "--cpus-per-task",
        "error": "--error",
        "ntasks": "--ntasks",
        "ntasks_per_node": "--ntasks-per-node",
        "nodes": "--nodes",
        "oom_kill_step": "--oom-kill-step",
        "partition": "--partition",
        "thread_spec": "--thread-spec",
        "walltime": "--time",
        "mem": "--mem",
        "mincpus": "--mincpus",
        "nodelist": "--nodelist",
        "exclude": "--exclude",
        "mem_per_cpu": "--mem-per-cpu",
        "cpus_per_gpu": "--cpus-per-gpu",
    }

    for key, flag in option_map.items():
        value = params.get(key)
        if value is not None:
            cmd_parts.append(f"{flag}={value}")

    bool_flags = {
        "no_requeue": "--no-requeue",
        "requeue": "--requeue",
        "use_min_nodes": "--use-min-nodes",
    }

    for key, flag in bool_flags.items():
        if params.get(key):
            cmd_parts.append(flag)

    cmd_parts.append('--wrap="sleep 6d"')
    return " ".join(cmd_parts)


def expand_node_list(nodelist):
    """Expand SLURM node list format to individual node names.

    Examples:
        "cn-1041" -> ["cn-1041"]
        "cn-[1041,1053-1055]" -> ["cn-1041", "cn-1053", "cn-1054", "cn-1055"]
        "cn-[1041],gn-[50-52]" -> ["cn-1041", "gn-50", "gn-51", "gn-52"]
    """
    nodes = []
    node_groups = []
    current = ""
    bracket_depth = 0

    for char in nodelist:
        if char == "[":
            bracket_depth += 1
            current += char
        elif char == "]":
            bracket_depth -= 1
            current += char
        elif char == "," and bracket_depth == 0:
            if current.strip():
                node_groups.append(current.strip())
            current = ""
        else:
            current += char

    if current.strip():
        node_groups.append(current.strip())

    for group in node_groups:
        match = re.match(r"^(\S+?)\[([^\]]+)\]$", group)
        if match:
            prefix = match.group(1)
            ranges = match.group(2)
            for part in ranges.split(","):
                part = part.strip()
                if "-" in part:
                    start, end = part.split("-", 1)
                    for num in range(int(start), int(end) + 1):
                        nodes.append(f"{prefix}{num}")
                else:
                    nodes.append(f"{prefix}{part}")
        else:
            nodes.append(group)

    return nodes


def submit_and_wait_for_job(sbatch_cmd, host="gdk"):
    """Submit a SLURM job and wait for it to start running.

    Returns the first allocated node name.
    Raises RuntimeError if no nodes are found.
    """
    output = run_remote(sbatch_cmd, host)
    jobid = output.split()[-1]
    print(f"Slurm job id: {jobid}")

    is_running = ""
    while not is_running:
        time.sleep(5)
        is_running = run_remote(f"squeue -j {jobid} -t RUNNING -h", host)

    nodelist = run_remote(f"squeue -j {jobid} -h -o %N", host)
    nodes = expand_node_list(nodelist)

    if not nodes:
        raise RuntimeError(f"No nodes found for job {jobid}")

    node = nodes[0]
    print(f"Job allocated to node(s): {', '.join(nodes)}")

    # Wait for SSH on the node to become reachable (via the login host)
    print(f"Waiting for {node} to accept SSH connections...")
    for _ in range(12):
        result = subprocess.run(
            f"ssh {host} 'ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no {node} true'",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            break
        time.sleep(5)

    return node


def open_vscode(node, directory=None):
    """Open VSCode connected to a remote node via SSH.

    If directory is given, opens that folder. Otherwise opens the VSCode
    welcome screen on the remote node.
    """
    if directory:
        vscode_uri = f"vscode-remote://ssh-remote+{node}{directory}"
        run_command(f"code --folder-uri '{vscode_uri}'")
    else:
        run_command(f"code --remote ssh-remote+{node}")


def _is_managed_job(name):
    """Check if a job name was created by slurm-code."""
    return any(name.startswith(p) for p in _KNOWN_PREFIXES)


def list_managed_jobs(host="gdk", all_states=False):
    """List slurm-code managed jobs using sacct.

    Uses sacct with a pipe delimiter to reliably parse output.
    Matches jobs whose name starts with any known prefix (sc-, slurm-code-).
    Returns a list of dicts with keys: jobid, name, partition, reqmem,
    reqcpus, timelimit, elapsed, state.
    """
    states = "RUNNING,PENDING" if all_states else "RUNNING"
    cmd = (
        f"sacct -X --state={states} --parsable2 "
        f'--format="jobid,jobname%30,partition,ReqMem,ReqCPUS,timelimit,elapsed,state"'
    )
    try:
        output = run_remote(cmd, host)
    except RuntimeError:
        return []

    if not output:
        return []

    jobs = []
    lines = output.strip().splitlines()
    # --parsable2 includes a header line; skip it
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) < 8:
            continue
        name = parts[1].strip()
        if not _is_managed_job(name):
            continue
        jobs.append(
            {
                "jobid": parts[0].strip(),
                "name": name,
                "partition": parts[2].strip(),
                "reqmem": parts[3].strip(),
                "reqcpus": parts[4].strip(),
                "timelimit": parts[5].strip(),
                "elapsed": parts[6].strip(),
                "state": parts[7].strip(),
            }
        )
    return jobs


def get_job_node(jobid, host="gdk"):
    """Get the node list for a running job via squeue."""
    try:
        return run_remote(f"squeue -j {jobid} -h -o %N", host)
    except RuntimeError:
        return None


def cancel_managed_jobs(host="gdk", job_id=None, job_name=None, cancel_all=False):
    """Cancel slurm-code managed jobs.

    Exactly one of job_id, job_name, or cancel_all must be specified.
    """
    if job_id:
        run_remote(f"scancel {job_id}", host)
        print(f"Cancelled job {job_id}")
    elif job_name:
        # If user passed a bare name without any known prefix, add the current one
        if not _is_managed_job(job_name):
            job_name = f"{JOB_NAME_PREFIX}{job_name}"
        run_remote(f"scancel --name={job_name}", host)
        print(f"Cancelled jobs with name {job_name}")
    elif cancel_all:
        jobs = list_managed_jobs(host, all_states=True)
        if not jobs:
            print("No slurm-code jobs to cancel.")
            return
        job_ids = " ".join(j["jobid"] for j in jobs)
        run_remote(f"scancel {job_ids}", host)
        print(f"Cancelled {len(jobs)} slurm-code job(s)")
    else:
        raise ValueError("Must specify job_id, job_name, or cancel_all")
