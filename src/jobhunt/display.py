from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table
from jobhunt.models import Job


def display_jobs_table(
    jobs: list[Job],
    console: Console | None = None,
    limit: int | None = None,
    new_job_ids: set[str] | None = None,
) -> None:
    con = console or Console()

    if not jobs:
        con.print("[yellow]No jobs found matching your criteria.[/yellow]")
        return

    shown = jobs[:limit] if limit else jobs
    title = f"Found {len(jobs)} jobs"
    if limit and limit < len(jobs):
        title += f" (showing {len(shown)})"

    # Print NEW summary if applicable
    if new_job_ids:
        new_count = sum(1 for j in shown if j.id in new_job_ids)
        if new_count > 0:
            con.print(f"[bold green]{new_count} new job{'s' if new_count != 1 else ''} since last search[/bold green]\n", highlight=False)

    table = Table(title=title, show_lines=False, expand=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Company", style="cyan", ratio=2, no_wrap=True, overflow="ellipsis")
    table.add_column("Title", style="green", ratio=4, no_wrap=True, overflow="ellipsis")
    table.add_column("Location", style="yellow", ratio=2, no_wrap=True, overflow="ellipsis")
    table.add_column("ATS", style="dim", width=6)

    for i, job in enumerate(shown, 1):
        row_num = "[bold green]NEW[/bold green]" if new_job_ids and job.id in new_job_ids else str(i)
        table.add_row(
            row_num,
            job.company,
            job.title,
            job.location or "-",
            job.platform.value[:5],
        )
    con.print(table)

    # Print URLs below the table
    con.print()
    for i, job in enumerate(shown, 1):
        con.print(f"  [dim]{i:>3}.[/dim] [blue underline]{job.url}[/blue underline]")


def export_json(jobs: list[Job], path: Path) -> None:
    data = [job.model_dump(mode="json") for job in jobs]
    path.write_text(json.dumps(data, indent=2, default=str))
