"""Click-based CLI for slurm-code."""

import os
import sys

import click

from slurm_code.config import (
    coerce_profile_value,
    get_config_path,
    get_profile,
    load_config,
)
from slurm_code.core import (
    add_bashrc_hook,
    build_sbatch_command,
    cancel_managed_jobs,
    check_remote_directory,
    derive_job_name,
    ensure_bashrc_hook,
    list_managed_jobs,
    open_vscode,
    submit_and_wait_for_job,
)


@click.group()
@click.option(
    "--host", "-H", default="gdk", show_default=True, help="SSH host alias."
)
@click.pass_context
def slurm_code(ctx, host):
    """Submit and manage SLURM jobs on GenomeDK with VSCode integration."""
    ctx.ensure_object(dict)
    ctx.obj["host"] = host


@slurm_code.command()
@click.argument("directory", required=False, default=None)
@click.option("-A", "--account", help="Charge job to specified account.")
@click.option(
    "-c", "--cpus-per-task", default="1", show_default=True, help="CPUs per task."
)
@click.option("-e", "--error", help="File for batch script's standard error.")
@click.option("-J", "--job-name", default=None, help="Job name (default: sc-<dir basename>).")
@click.option(
    "-n", "--ntasks", default="1", show_default=True, help="Number of tasks."
)
@click.option("--no-requeue", is_flag=True, help="Do not requeue the job.")
@click.option("--ntasks-per-node", help="Tasks per node.")
@click.option("-N", "--nodes", help="Number of nodes (N = min[-max]).")
@click.option(
    "--oom-kill-step", type=click.Choice(["0", "1"]), help="OOMKillStep behaviour."
)
@click.option("-p", "--partition", help="Partition requested.")
@click.option("--requeue", is_flag=True, help="Permit the job to be requeued.")
@click.option("--thread-spec", help="Count of reserved threads.")
@click.option(
    "-t",
    "--walltime",
    default="08:00:00",
    show_default=True,
    help="Time limit (e.g. 08:00:00).",
)
@click.option("--use-min-nodes", is_flag=True, help="Prefer smaller node count.")
@click.option("--mem", help="Minimum real memory (e.g. 4g).")
@click.option("--mincpus", help="Minimum logical processors per node.")
@click.option("-w", "--nodelist", help="Request specific hosts.")
@click.option("-x", "--exclude", help="Exclude specific hosts.")
@click.option(
    "-m",
    "--mem-per-cpu",
    default="8g",
    show_default=True,
    help="Memory per allocated CPU.",
)
@click.option("--cpus-per-gpu", help="CPUs per allocated GPU.")
@click.option(
    "--pixi",
    is_flag=True,
    default=False,
    help="Activate pixi environment from DIRECTORY on the allocated node.",
)
@click.option(
    "-P",
    "--profile",
    default=None,
    help="Submit profile from config file.",
)
@click.pass_context
def submit(ctx, directory, profile, pixi, **kwargs):
    """Submit a SLURM job, wait for allocation, and open VSCode.

    DIRECTORY is the optional path on the remote host to open in VSCode.
    If omitted, VSCode opens the welcome screen on the allocated node.
    """
    host = ctx.obj["host"]

    if directory is not None:
        # Expand ~ to $HOME for remote resolution
        if not directory.startswith("/"):
            directory = f"$HOME/{directory}"

        expanded = check_remote_directory(directory, host)
        if not expanded:
            click.echo(
                f"Error: Directory '{directory}' does not exist on {host}",
                err=True,
            )
            sys.exit(1)

        directory = expanded

    # Load profile settings
    config = load_config()
    profile_values = get_profile(config, profile)

    # Resolve --pixi: CLI flag wins, then profile value
    if not pixi and "pixi" in profile_values:
        pixi = coerce_profile_value("pixi", profile_values["pixi"])

    if pixi and directory is None:
        click.echo(
            "Error: --pixi requires a DIRECTORY argument (the pixi project path).",
            err=True,
        )
        sys.exit(1)

    params = {}
    if directory is not None:
        params["directory"] = directory

    # Map click option names to param dict keys
    key_map = {
        "account": "account",
        "cpus_per_task": "cpus_per_task",
        "error": "error",
        "job_name": "job_name",
        "ntasks": "ntasks",
        "no_requeue": "no_requeue",
        "ntasks_per_node": "ntasks_per_node",
        "nodes": "nodes",
        "oom_kill_step": "oom_kill_step",
        "partition": "partition",
        "requeue": "requeue",
        "thread_spec": "thread_spec",
        "walltime": "walltime",
        "use_min_nodes": "use_min_nodes",
        "mem": "mem",
        "mincpus": "mincpus",
        "nodelist": "nodelist",
        "exclude": "exclude",
        "mem_per_cpu": "mem_per_cpu",
        "cpus_per_gpu": "cpus_per_gpu",
    }

    for click_key, param_key in key_map.items():
        source = ctx.get_parameter_source(click_key)
        if source == click.core.ParameterSource.COMMANDLINE:
            # Explicit CLI flag always wins
            value = kwargs.get(click_key)
            if value is not None and value is not False:
                params[param_key] = value
        elif param_key in profile_values:
            # Profile value (includes DEFAULT inheritance)
            params[param_key] = coerce_profile_value(
                param_key, profile_values[param_key]
            )
        else:
            # Fall back to Click default
            value = kwargs.get(click_key)
            if value is not None and value is not False:
                params[param_key] = value

    sbatch_cmd = build_sbatch_command(params)

    try:
        node = submit_and_wait_for_job(
            sbatch_cmd, host, pixi_dir=directory if pixi else None
        )
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Set up bashrc hook for pixi activation
    if pixi:
        if not ensure_bashrc_hook(host):
            if click.confirm(
                "Add pixi activation hook to ~/.bashrc on the cluster? "
                "(Required for VSCode terminals to auto-activate the pixi environment)"
            ):
                add_bashrc_hook(host)
                click.echo("Added pixi activation hook to ~/.bashrc.")
            else:
                click.echo(
                    "Skipped. To activate pixi manually, add this line to ~/.bashrc:\n"
                    "  [ -f .slurm-code-pixi-env.sh ] && source .slurm-code-pixi-env.sh"
                )

    open_vscode(node, directory)


@slurm_code.command()
@click.option(
    "--all-states", is_flag=True, help="Include PENDING jobs (default: RUNNING only)."
)
@click.pass_context
def jobs(ctx, all_states):
    """List running slurm-code managed jobs."""
    host = ctx.obj["host"]
    job_list = list_managed_jobs(host, all_states=all_states)

    if not job_list:
        click.echo("No slurm-code jobs found.")
        return

    # Header matching sacct format
    click.echo(
        f"{'JOBID':>10}  {'NAME':<30}  {'PARTITION':<12}  {'REQMEM':<8}  "
        f"{'CPUS':<6}  {'TIMELIMIT':<12}  {'ELAPSED':<12}  {'STATE':<10}"
    )
    click.echo("-" * 106)
    for j in job_list:
        click.echo(
            f"{j['jobid']:>10}  {j['name']:<30}  {j['partition']:<12}  "
            f"{j['reqmem']:<8}  {j['reqcpus']:<6}  {j['timelimit']:<12}  "
            f"{j['elapsed']:<12}  {j['state']:<10}"
        )


@slurm_code.command()
@click.argument("job_id_or_name", required=False)
@click.option("--all", "cancel_all", is_flag=True, help="Cancel all slurm-code jobs.")
@click.pass_context
def cancel(ctx, job_id_or_name, cancel_all):
    """Cancel slurm-code managed jobs.

    Optionally specify a JOB_ID_OR_NAME to cancel a specific job.
    Use --all to cancel all slurm-code jobs.
    """
    host = ctx.obj["host"]

    if not job_id_or_name and not cancel_all:
        click.echo("Error: Specify a job ID/name or use --all.", err=True)
        sys.exit(1)

    try:
        if cancel_all:
            cancel_managed_jobs(host, cancel_all=True)
        elif job_id_or_name and job_id_or_name.isdigit():
            cancel_managed_jobs(host, job_id=job_id_or_name)
        else:
            cancel_managed_jobs(host, job_name=job_id_or_name)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@slurm_code.command()
@click.argument("directory")
@click.pass_context
def reconnect(ctx, directory):
    """Reconnect VSCode to a running slurm-code job.

    DIRECTORY is the path on the remote host (used to match the job name).
    """
    host = ctx.obj["host"]

    # Expand ~ to $HOME for remote resolution
    if not directory.startswith("/"):
        directory = f"$HOME/{directory}"

    expanded = check_remote_directory(directory, host)
    if not expanded:
        click.echo(
            f"Error: Directory '{directory}' does not exist on {host}",
            err=True,
        )
        sys.exit(1)

    directory = expanded
    basename = os.path.basename(directory.rstrip("/"))

    from slurm_code.core import expand_node_list, get_job_node

    running_jobs = list_managed_jobs(host, all_states=False)
    matches = [j for j in running_jobs if j["name"].endswith(f"-{basename}")]

    if not matches:
        click.echo(
            f"No running job found matching '{basename}'.\n"
            f"Use 'slurm-code jobs --all-states' to see all jobs.",
            err=True,
        )
        sys.exit(1)

    if len(matches) == 1:
        job = matches[0]
    else:
        click.echo("Multiple matching jobs found:")
        for i, j in enumerate(matches, 1):
            click.echo(f"  [{i}] {j['jobid']}  {j['elapsed']}  {j['state']}")

        choice = click.prompt(
            "Select job number", type=click.IntRange(1, len(matches))
        )
        job = matches[choice - 1]

    # Get node allocation via squeue
    nodelist = get_job_node(job["jobid"], host)
    if not nodelist:
        click.echo(f"Job {job['jobid']} has no node allocated yet.", err=True)
        sys.exit(1)

    nodes = expand_node_list(nodelist)
    node = nodes[0]

    click.echo(f"Connecting to {node} (job {job['jobid']})...")
    open_vscode(node, directory)


@slurm_code.command()
def profiles():
    """Show config file path and available submit profiles."""
    path = get_config_path()
    click.echo(f"Config file: {path}")

    if not path.exists():
        click.echo("No config file found.")
        return

    config = load_config()
    defaults = config.defaults()

    if defaults:
        click.echo("\n[DEFAULT]")
        for key, value in defaults.items():
            click.echo(f"  {key} = {value}")

    sections = config.sections()
    if not sections and not defaults:
        click.echo("No profiles defined.")
        return

    for section in sections:
        click.echo(f"\n[{section}]")
        for key, value in config[section].items():
            click.echo(f"  {key} = {value}")
