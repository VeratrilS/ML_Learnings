"""
Add-only schema sync for the Job Radar tables.

`table.create(checkfirst=True)` never alters an existing table, so a column added to a model after the table
exists in production (Postgres) breaks every query with UndefinedColumn. On startup this adds any model column
that the live table lacks — nullable, no default, never drops or changes anything — so it is safe to repeat.
"""
from sqlalchemy import inspect, text

from api.core.db import engine


def _models():
    from api.domain import job_radar
    return [m for m in (getattr(job_radar, n, None) for n in ("JobOpportunity", "JobRadarScanLog", "JobRadarProfile"))
            if m is not None]


def add_missing_columns(bind=None):
    """Returns the list of 'table.column' names that were added."""
    bind = bind or engine
    added = []
    try:
        insp = inspect(bind)
        existing_tables = set(insp.get_table_names())
        with bind.begin() as conn:
            for model in _models():
                table = model.__table__
                if table.name not in existing_tables:
                    continue  # create(checkfirst) makes it with every column
                have = {c["name"] for c in insp.get_columns(table.name)}
                for col in table.columns:
                    if col.name in have:
                        continue
                    ddl_type = col.type.compile(dialect=bind.dialect)
                    if bind.dialect.name == "postgresql":
                        conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN IF NOT EXISTS "{col.name}" {ddl_type}'))
                    else:
                        conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {ddl_type}'))
                    added.append(f"{table.name}.{col.name}")
        if added:
            print(f"job radar schema: added {', '.join(added)}")
    except Exception as e:  # never block startup
        print(f"job radar schema sync skipped: {e}")
    return added
