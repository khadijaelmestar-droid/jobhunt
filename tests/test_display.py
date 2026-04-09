from __future__ import annotations

from io import StringIO

from rich.console import Console

from jobhunt.display import display_jobs_table


class TestNewBadges:
    """Jobs in new_job_ids get a [NEW] badge instead of a row number."""

    def test_new_badge_shown_for_new_jobs(self, sample_jobs):
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        new_ids = {sample_jobs[0].id}  # "1001" is new
        display_jobs_table(sample_jobs, console=console, new_job_ids=new_ids)
        text = output.getvalue()
        assert "NEW" in text

    def test_no_badge_when_no_new_ids(self, sample_jobs):
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        display_jobs_table(sample_jobs, console=console, new_job_ids=set())
        text = output.getvalue()
        assert "NEW" not in text

    def test_no_badge_when_new_job_ids_is_none(self, sample_jobs):
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        display_jobs_table(sample_jobs, console=console)
        text = output.getvalue()
        assert "NEW" not in text

    def test_summary_count_printed(self, sample_jobs):
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        new_ids = {sample_jobs[0].id, sample_jobs[2].id}
        display_jobs_table(sample_jobs, console=console, new_job_ids=new_ids)
        text = output.getvalue()
        assert "2 new" in text.lower()
