# Alembic Migration Guide (Chaldea-specific)

## When to Use

- Adding Alembic to a service that doesn't have it (T2)
- Creating a migration when the DB schema changes
- Setting up async Alembic configuration

## Input

- Service name
- Sync or async (from analysis_report)
- Current models (`models.py`)

## Steps

### 1. Initialize Alembic (if absent from the service)

```bash
cd services/<service>

# Add alembic to requirements.txt
echo "alembic" >> requirements.txt

# Initialize
alembic init alembic
```

### 2. Configure `alembic.ini`

```ini
[alembic]
script_location = alembic
sqlalchemy.url = mysql+pymysql://%(DB_USER)s:%(DB_PASSWORD)s@%(DB_HOST)s:3306/mydatabase
```

### 3. Configure `alembic/env.py`

#### Sync services (user, character, inventory, character-attributes)

```python
from app.models import Base
from app.config import settings

def run_migrations_online():
    from sqlalchemy import create_engine

    url = f"mysql+pymysql://{settings.db_user}:{settings.db_password}@{settings.db_host}:3306/mydatabase"
    connectable = create_engine(url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            # Important: do not touch tables owned by other services
            include_object=lambda obj, name, type_, reflected, compare_to: (
                type_ != "table" or name in OWN_TABLES
            ),
        )
        with context.begin_transaction():
            context.run_migrations()
```

#### Async services (locations, skills, battle)

```python
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.models import Base
from app.config import settings

def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        include_object=lambda obj, name, type_, reflected, compare_to: (
            type_ != "table" or name in OWN_TABLES
        ),
    )
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    url = f"mysql+aiomysql://{settings.db_user}:{settings.db_password}@{settings.db_host}:3306/mydatabase"
    connectable = create_async_engine(url)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

asyncio.run(run_migrations_online())
```

### 4. Define OWN_TABLES

Each service "owns" its tables. Define the list from `models.py`:

```python
# In env.py — tables owned by THIS service
OWN_TABLES = {"characters", "character_requests", "character_titles"}
```

This is **critically important** — without the filter, Alembic will try to drop tables belonging to other services!

### 5. Create the initial migration

```bash
cd services/<service>
alembic revision --autogenerate -m "initial migration"
```

**Review the generated file:**
- Only tables from OWN_TABLES
- Column types match the current DB
- No `drop_table` for other services' tables
- No changes to existing tables (initial = create only)

### 6. Create a migration for changes

```bash
alembic revision --autogenerate -m "add column_name to table_name"
```

**Naming convention:**
- `add_<column>_to_<table>` — new column
- `create_<table>` — new table
- `alter_<column>_in_<table>` — type change
- `drop_<column>_from_<table>` — column removal

### 7. Verify rollback

Ensure `downgrade()` is correct:
```python
def downgrade():
    op.drop_column('table_name', 'column_name')
```

## Important Chaldea Rules

1. **Shared DB** — all services use one MySQL `mydatabase`. Filter with `include_object`!
2. **Initial migration = create only** — do not modify existing tables
3. **Separate commit** — adding Alembic is separate from the main task
4. **photo-service** — special case: no SQLAlchemy models, create them first
5. **SQL backups** — do not delete `docker/mysql/backups/`, keep as fallback

## Result

- `alembic/` directory in the service
- `alembic.ini` configured
- `alembic/env.py` with OWN_TABLES filter
- Initial or feature migration created and verified
- `alembic` added to `requirements.txt`

## Agents

- **Primary:** Backend Developer
