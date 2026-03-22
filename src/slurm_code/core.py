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

    A short timestamp suffix ensures uniqueness when multiple jobs target
    the same directory.

    E.g. ~/projects/my-analysis -> sc-my-analysis-0318-1430
         None -> sc-20260302-143022
    """
    ts = datetime.now().strftime("%m%d-%H%M")
    if directory:
        basename = os.path.basename(directory.rstrip("/"))
        return f"{JOB_NAME_PREFIX}{basename}-{ts}"
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


PIXI_ENV_SCRIPT = ".slurm-code-pixi-env.sh"
SLURM_ENV_SCRIPT = ".slurm-code-slurm-env.sh"
LOADER_SCRIPT = ".slurm-code-env.sh"  # written to ~ on each submit

# Mapping from scontrol field names to SLURM environment variable names
_SCONTROL_TO_ENV = {
    "JobId": "VS_SLURM_JOB_ID",
    "JobName": "VS_SLURM_JOB_NAME",
    "Partition": "VS_SLURM_JOB_PARTITION",
    "Account": "VS_SLURM_JOB_ACCOUNT",
    "NumNodes": "VS_SLURM_JOB_NUM_NODES",
    "NumCPUs": "VS_SLURM_CPUS_ON_NODE",
    "NodeList": "VS_SLURM_JOB_NODELIST",
    "TimeLimit": "VS_SLURM_TIMELIMIT",
    "WorkDir": "VS_SLURM_SUBMIT_DIR",
}


def _parse_scontrol_output(output):
    """Parse scontrol show job output into a dict of key=value pairs."""
    fields = {}
    for token in re.split(r"\s+", output):
        if "=" in token:
            key, _, value = token.partition("=")
            fields[key] = value
    return fields


def setup_slurm_env(jobid, directory, host="gdk"):
    """Write SLURM environment variables for a job to a script in the project directory.

    Queries ``scontrol show job`` and writes export statements to
    ``<directory>/.slurm-code-slurm-env.sh`` so that VSCode terminals
    have access to the standard SLURM variables.

    Also extracts mem-per-cpu from ReqTRES when available.

    Returns True on success, False on failure.
    """
    try:
        output = run_remote(f"scontrol show job {jobid}", host)
    except RuntimeError:
        return False

    fields = _parse_scontrol_output(output)

    lines = ["# SLURM environment variables for job (generated by slurm-code)"]
    for scontrol_key, env_var in _SCONTROL_TO_ENV.items():
        value = fields.get(scontrol_key)
        if value is not None:
            lines.append(f"export {env_var}={value!r}")

    # Extract mem-per-cpu from MinMemoryCPU (e.g. "8G")
    mem_per_cpu = fields.get("MinMemoryCPU")
    if mem_per_cpu:
        # Convert to MB as SLURM does (e.g. "8G" -> "8192")
        match = re.match(r"^(\d+)([KMGT]?)$", mem_per_cpu, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            unit = match.group(2).upper()
            multipliers = {"": 1, "K": 1, "M": 1, "G": 1024, "T": 1024 * 1024}
            mb_value = num * multipliers.get(unit, 1)
            lines.append(f"export VS_SLURM_MEM_PER_CPU={mb_value!r}")

    # CPUs per task from ReqTRES or TresPerTask
    cpus_per_task = fields.get("CPUs/Task")
    if cpus_per_task:
        lines.append(f"export VS_SLURM_CPUS_PER_TASK={cpus_per_task!r}")

    # NTasks
    ntasks = fields.get("NumTasks")
    if ntasks:
        lines.append(f"export VS_SLURM_NTASKS={ntasks!r}")

    script_content = "\n".join(lines) + "\n"
    script_path = f"{directory}/{SLURM_ENV_SCRIPT}"
    write_cmd = f"ssh {host} 'cat > {script_path}'"
    write_result = subprocess.run(
        write_cmd,
        shell=True,
        input=script_content,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return write_result.returncode == 0


def setup_pixi_env(node, directory, host="gdk"):
    """Set up pixi environment activation for a project directory.

    Runs ``pixi shell-hook`` on the login host (which shares the home
    filesystem with compute nodes) and writes the output to
    ``<directory>/.slurm-code-pixi-env.sh``.

    Returns True on success, False on failure.
    """
    # Run pixi shell-hook on the login host — pixi is installed there and
    # the home filesystem is shared with compute nodes.
    # Use the default pixi install path since non-interactive SSH sessions
    # may not have ~/.pixi/bin on PATH.
    result = subprocess.run(
        f"ssh {host} 'cd {directory} && $HOME/.pixi/bin/pixi shell-hook --shell bash'",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        return False

    hook_script = result.stdout.strip()
    if not hook_script:
        return False

    # Write the activation script into the project directory
    script_path = f"{directory}/{PIXI_ENV_SCRIPT}"
    write_cmd = f"ssh {host} 'cat > {script_path}'"
    write_result = subprocess.run(
        write_cmd,
        shell=True,
        input=hook_script + "\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return write_result.returncode == 0


def write_loader_script(directory, host="gdk"):
    """Write ~/.slurm-code-env.sh with absolute source lines for the project.

    This loader is overwritten on each submit so it always points to the
    current project's SLURM env script.  Pixi activation is handled
    separately via a relative-path hook so it only fires when the shell
    starts in the project directory (as VSCode terminals do).
    """
    slurm_path = f"{directory}/{SLURM_ENV_SCRIPT}"
    lines = [
        "# Generated by slurm-code — do not edit, overwritten on each submit",
        f"[ -f {slurm_path} ] && source {slurm_path}",
    ]
    content = "\n".join(lines) + "\n"
    cmd = f"ssh {host} 'cat > ~/{LOADER_SCRIPT}'"
    subprocess.run(
        cmd,
        shell=True,
        input=content,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )


def ensure_bashrc_hook(host="gdk"):
    """Check if ~/.bashrc already sources the slurm-code loader.

    Returns True if present, False otherwise.
    """
    result = subprocess.run(
        f"ssh {host} 'grep -qF {LOADER_SCRIPT} ~/.bashrc'",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def add_bashrc_hook(host="gdk"):
    """Append slurm-code hooks to ~/.bashrc on the remote.

    The loader script (absolute path in ~) provides SLURM env vars for
    every shell.  The pixi script uses a relative path so it only
    activates when the shell starts in the project directory.
    """
    snippet = (
        "\n# Added by slurm-code for environment activation\n"
        f"[ -f ~/{LOADER_SCRIPT} ] && source ~/{LOADER_SCRIPT}\n"
        f"[ -f {PIXI_ENV_SCRIPT} ] && source {PIXI_ENV_SCRIPT}\n"
    )
    cmd = f"ssh {host} 'cat >> ~/.bashrc'"
    subprocess.run(
        cmd,
        shell=True,
        input=snippet,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )


def submit_and_wait_for_job(sbatch_cmd, host="gdk", directory=None, pixi_dir=None):
    """Submit a SLURM job and wait for it to start running.

    If *directory* is given, writes SLURM environment variables to a
    script in the project directory so VSCode terminals can access them.

    If *pixi_dir* is given, sets up pixi environment activation on the
    allocated node after SSH connectivity is confirmed.

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

    # Remove any stale host key before checking connectivity, so that
    # the StrictHostKeyChecking=accept-new probe adds the current key
    # and VSCode won't prompt about a changed fingerprint.
    clear_host_key(node)

    # Wait for SSH on the node to become reachable.
    # We connect locally (relying on ProxyJump in ~/.ssh/config) so that
    # StrictHostKeyChecking=accept-new populates the *local* known_hosts —
    # preventing VSCode from prompting for the host fingerprint.
    print(f"Waiting for {node} to accept SSH connections...")
    for _ in range(12):
        result = subprocess.run(
            f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new {node} true",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            break
        time.sleep(5)

    if directory:
        if not setup_slurm_env(jobid, directory, host):
            print("Warning: Failed to write SLURM environment variables.")

    if pixi_dir:
        print(f"Setting up pixi environment from {pixi_dir}...")
        if not setup_pixi_env(node, pixi_dir, host):
            print(
                "Warning: Failed to set up pixi environment. "
                "Check that pixi is installed and the directory contains a pixi project."
            )

    if directory:
        write_loader_script(directory, host=host)

    return node


def clear_host_key(node):
    """Remove a stale SSH host key for a compute node.

    Compute nodes get reimaged frequently, so their host keys change.
    Clearing the old key avoids an interactive fingerprint mismatch prompt
    when VSCode connects.
    """
    subprocess.run(
        ["ssh-keygen", "-R", node],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


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
        # Names now include a timestamp suffix, so match by prefix
        jobs = list_managed_jobs(host, all_states=True)
        matches = [j for j in jobs if j["name"].startswith(job_name)]
        if not matches:
            raise RuntimeError(f"No jobs found matching '{job_name}'")
        match_ids = " ".join(j["jobid"] for j in matches)
        run_remote(f"scancel {match_ids}", host)
        print(f"Cancelled {len(matches)} job(s) matching '{job_name}'")
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
