from sqlalchemy import create_engine, inspect, text

from api.domain.job_migrations import add_missing_columns
from api.domain.job_radar import JobOpportunity


def test_adds_missing_columns_once(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with eng.begin() as conn:  # an "old" production table with only a few columns
        conn.execute(text(f"CREATE TABLE {JobOpportunity.__table__.name} (id INTEGER PRIMARY KEY, external_id VARCHAR(80), company VARCHAR(120))"))
    added = add_missing_columns(eng)
    have = {c["name"] for c in inspect(eng).get_columns(JobOpportunity.__table__.name)}
    assert {c.name for c in JobOpportunity.__table__.columns} <= have
    assert f"{JobOpportunity.__table__.name}.portal_url" in added
    assert add_missing_columns(eng) == []  # idempotent


def test_relaxes_not_null_only_on_postgres_semantics(tmp_path):
    # SQLite can't ALTER nullability; the function must not crash there and must leave columns alone.
    eng = create_engine(f"sqlite:///{tmp_path / 'n.db'}")
    with eng.begin() as conn:
        conn.execute(text(f"CREATE TABLE {JobOpportunity.__table__.name} (id INTEGER PRIMARY KEY, eligible_batches VARCHAR(80) NOT NULL)"))
    added = add_missing_columns(eng)
    assert not any("now nullable" in a for a in added)
