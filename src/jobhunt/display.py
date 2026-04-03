from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table
from jobhunt.models import Job


def display_jobs_table(jobs: list[Job], console: Console | None = None, limit: int | None = None) -> None:
    con = console or Console()

    if not jobs:
        con.print("[yellow]No jobs found matching your criteria.[/yellow]")
        return

    shown = jobs[:limit] if limit else jobs
    title = f"Found {len(jobs)} jobs"
    if limit and limit < len(jobs):
        title += f" (showing {len(shown)})"

    # Use a compact format: Company | Title | Location | ATS
    # Then print the URL on a separate indented line for each job
    table = Table(title=title, show_lines=False, expand=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Company", style="cyan", ratio=2, no_wrap=True, overflow="ellipsis")
    table.add_column("Title", style="green", ratio=4, no_wrap=True, overflow="ellipsis")
    table.add_column("Location", style="yellow", ratio=2, no_wrap=True, overflow="ellipsis")
    table.add_column("ATS", style="dim", width=6)

    for i, job in enumerate(shown, 1):
        table.add_row(
            str(i),
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
