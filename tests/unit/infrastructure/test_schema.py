from video_app.infrastructure.schema import generation_jobs, projects


def test_telugu_project_fields_belong_to_projects_not_generation_jobs() -> None:
    assert "preset" in projects.c
    assert "titles_and_credits_within_target" in projects.c
    assert "preset" not in generation_jobs.c
    assert "titles_and_credits_within_target" not in generation_jobs.c


def test_timeline_render_uses_the_canonical_generation_job_table() -> None:
    assert {
        "timeline_render_project_id",
        "timeline_render_timeline_id",
        "timeline_render_timeline_revision",
        "timeline_render_timeline_fingerprint",
        "timeline_render_required_backend",
        "timeline_render_required_backend_revision",
        "timeline_render_manifest_fingerprint",
        "timeline_render_manifest",
    }.issubset(generation_jobs.c.keys())
