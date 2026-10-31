"""prosho: mentors, milestones, feedback, commit timeline, page stats

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-21

ProSho Phase 3, "work over time" (docs/prosho/BETA_PLAN.md §8, §12).

- project_mentors: an admin assigns LVAMO mentors to a project. A mentor
  sees the project (even when private), leaves feedback and reviews
  milestones; the public page only says "Mentored via LVAMO".
- milestones: set by the student; a mentor marks completed ones reviewed.
- feedback: mentor <-> student threads (one level of replies), optionally
  about a milestone or claim. Never shown on the public page.
- repo_events: commits on the connected repo's default branch, read from
  GitHub on every manifest sync. projects.repo_private decides whether
  commit messages may appear on the public page (activity counts always do).
- page_stats_daily: aggregate counts only (page views, clicks to the LVAMO
  hub) per project, day and referring domain. No IPs, no cookies (§11).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE prosho.projects ADD COLUMN repo_private BOOLEAN")
    op.execute("""
        CREATE TABLE prosho.project_mentors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES prosho.projects(id) ON DELETE CASCADE,
            mentor_id UUID NOT NULL REFERENCES prosho.users(id) ON DELETE CASCADE,
            assigned_by UUID REFERENCES prosho.users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_prosho_project_mentors_pair UNIQUE (project_id, mentor_id)
        );
    """)
    op.execute("CREATE INDEX ix_prosho_project_mentors_mentor_id ON prosho.project_mentors (mentor_id)")
    op.execute("""
        CREATE TABLE prosho.milestones (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES prosho.projects(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            due_on DATE,
            completed_at TIMESTAMPTZ,
            reviewed_by UUID REFERENCES prosho.users(id) ON DELETE SET NULL,
            reviewed_at TIMESTAMPTZ,
            position INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT prosho_milestones_review_needs_completion
                CHECK (reviewed_at IS NULL OR completed_at IS NOT NULL)
        );
    """)
    op.execute("CREATE INDEX ix_prosho_milestones_project_id ON prosho.milestones (project_id)")
    op.execute("""
        CREATE TABLE prosho.feedback (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES prosho.projects(id) ON DELETE CASCADE,
            author_id UUID REFERENCES prosho.users(id) ON DELETE SET NULL,
            parent_id UUID REFERENCES prosho.feedback(id) ON DELETE CASCADE,
            milestone_id UUID REFERENCES prosho.milestones(id) ON DELETE SET NULL,
            claim_id UUID REFERENCES prosho.claims(id) ON DELETE SET NULL,
            body TEXT NOT NULL,
            resolved_at TIMESTAMPTZ,
            resolved_by UUID REFERENCES prosho.users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX ix_prosho_feedback_project_time ON prosho.feedback (project_id, created_at)")
    op.execute("""
        CREATE TABLE prosho.repo_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES prosho.projects(id) ON DELETE CASCADE,
            commit_sha VARCHAR(40) NOT NULL,
            message VARCHAR(300) NOT NULL,
            author_login VARCHAR(100),
            committed_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_prosho_repo_events_project_commit UNIQUE (project_id, commit_sha)
        );
    """)
    op.execute("CREATE INDEX ix_prosho_repo_events_project_time ON prosho.repo_events (project_id, committed_at DESC)")
    op.execute("CREATE TYPE prosho.page_event_enum AS ENUM ('view', 'hub_click')")
    op.execute("""
        CREATE TABLE prosho.page_stats_daily (
            project_id UUID NOT NULL REFERENCES prosho.projects(id) ON DELETE CASCADE,
            day DATE NOT NULL,
            event prosho.page_event_enum NOT NULL,
            referrer_domain VARCHAR(100) NOT NULL DEFAULT '',
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (project_id, day, event, referrer_domain)
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prosho.page_stats_daily")
    op.execute("DROP TYPE IF EXISTS prosho.page_event_enum")
    op.execute("DROP TABLE IF EXISTS prosho.repo_events")
    op.execute("DROP TABLE IF EXISTS prosho.feedback")
    op.execute("DROP TABLE IF EXISTS prosho.milestones")
    op.execute("DROP TABLE IF EXISTS prosho.project_mentors")
    op.execute("ALTER TABLE prosho.projects DROP COLUMN IF EXISTS repo_private")
