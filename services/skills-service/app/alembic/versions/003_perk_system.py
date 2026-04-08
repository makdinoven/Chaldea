"""Replace SkillRank system with Perk system (FEAT-125)

Revision ID: 003_perk_system
Revises: 002_class_skill_trees
Create Date: 2026-04-08

Migration overview:
1. Defensive cross-table backfill: add `mob_template_skills.skill_id` (nullable) and
   backfill from `skill_ranks` while it still exists. Drop of the old `skill_rank_id`
   column on that table is left to character-service migration 016 (which owns the table).
   On a fresh CI database where `mob_template_skills` does not exist, this step is a no-op.
2. Rebuild `character_skills` to (character_id, skill_id, level, reset_available_at)
   shape with UNIQUE(character_id, skill_id). Backfills `skill_id` from `skill_ranks`
   if data exists; otherwise creates the new shape directly.
3. Create `skill_base_damage` and `skill_base_effects` tables. Copy rows from
   `skill_rank_damage`/`skill_rank_effects` rooted at the lowest-rank row of each skill,
   if those source tables still exist.
4. Drop `skill_rank_effects`, `skill_rank_damage`, `skill_ranks`.
5. Create `skill_perks`, `skill_perk_damage`, `skill_perk_effects`, `character_skill_perks`.

All steps are guarded with inspector checks for idempotency / fresh DBs.

Foreign-key names are introspected at runtime via `inspector.get_foreign_keys()` —
no hardcoded auto-generated names.

Deployment ordering note: this migration must run before character-service `016_repoint_mob_template_skills`,
because step 1 here reads from `skill_ranks` (still present) while step 4 drops it.
Skills-service starts before character-service in compose; both run alembic at startup.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003_perk_system'
down_revision = '002_class_skill_trees'
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return any(c['name'] == column for c in inspector.get_columns(table))


def _fk_name(inspector, table: str, column: str) -> str | None:
    if table not in inspector.get_table_names():
        return None
    for fk in inspector.get_foreign_keys(table):
        if column in (fk.get('constrained_columns') or []):
            return fk.get('name')
    return None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # ----------------------------------------------------------------
    # 1. Defensive backfill of mob_template_skills.skill_id (owned by character-service)
    # ----------------------------------------------------------------
    if 'mob_template_skills' in tables and 'skill_ranks' in tables:
        if not _has_column(inspector, 'mob_template_skills', 'skill_id'):
            op.add_column(
                'mob_template_skills',
                sa.Column('skill_id', sa.Integer(), nullable=True),
            )
            # Backfill (no-op if table empty)
            op.execute(
                """
                UPDATE mob_template_skills mts
                JOIN skill_ranks sr ON mts.skill_rank_id = sr.id
                SET mts.skill_id = sr.skill_id
                """
            )

    # ----------------------------------------------------------------
    # 2. Rebuild character_skills
    # ----------------------------------------------------------------
    if 'character_skills' in tables:
        if not _has_column(inspector, 'character_skills', 'skill_id'):
            op.add_column(
                'character_skills',
                sa.Column('skill_id', sa.Integer(), nullable=True),
            )
            if 'skill_ranks' in tables and _has_column(inspector, 'character_skills', 'skill_rank_id'):
                op.execute(
                    """
                    UPDATE character_skills cs
                    JOIN skill_ranks sr ON cs.skill_rank_id = sr.id
                    SET cs.skill_id = sr.skill_id
                    """
                )

        if not _has_column(inspector, 'character_skills', 'level'):
            op.add_column(
                'character_skills',
                sa.Column('level', sa.SmallInteger(), nullable=False, server_default='0'),
            )
        if not _has_column(inspector, 'character_skills', 'reset_available_at'):
            op.add_column(
                'character_skills',
                sa.Column('reset_available_at', sa.DateTime(), nullable=True),
            )

        # Dedupe rows that collide on (character_id, skill_id) BEFORE we drop
        # the skill_rank_id column. Multiple character_skills rows can map to
        # the same parent skill_id (different ranks of the same skill). For
        # each (character_id, skill_id) group we keep the row whose source
        # rank had the LOWEST rank_number (the cleanest base entry — prod is
        # test data only and progression is throwaway), with id ASC as a
        # stable tiebreaker. Requires MySQL 8+ (window functions).
        if _has_column(inspector, 'character_skills', 'skill_rank_id') and 'skill_ranks' in tables:
            op.execute(
                """
                DELETE FROM character_skills WHERE id IN (
                    SELECT id FROM (
                        SELECT cs.id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY cs.character_id, cs.skill_id
                                   ORDER BY sr.rank_number ASC, cs.id ASC
                               ) AS rn
                        FROM character_skills cs
                        JOIN skill_ranks sr ON sr.id = cs.skill_rank_id
                    ) ranked WHERE rn > 1
                )
                """
            )

        # Drop FK and column skill_rank_id if present
        if _has_column(inspector, 'character_skills', 'skill_rank_id'):
            fk_name = _fk_name(inspector, 'character_skills', 'skill_rank_id')
            if fk_name:
                op.drop_constraint(fk_name, 'character_skills', type_='foreignkey')
            op.drop_column('character_skills', 'skill_rank_id')

        # Wipe rows whose skill_id we could not resolve (orphans / no source data)
        op.execute("DELETE FROM character_skills WHERE skill_id IS NULL")

        # NOT NULL + FK to skills + UNIQUE(character_id, skill_id)
        op.alter_column(
            'character_skills', 'skill_id',
            existing_type=sa.Integer(),
            nullable=False,
        )
        # Refresh inspector after alterations
        inspector = sa.inspect(bind)
        existing_uqs = {uc['name'] for uc in inspector.get_unique_constraints('character_skills')}
        if 'uq_character_skill' not in existing_uqs:
            op.create_unique_constraint(
                'uq_character_skill', 'character_skills', ['character_id', 'skill_id'],
            )
        # FK to skills.id (only if skills table exists)
        if 'skills' in tables:
            existing_fks = {
                tuple(fk.get('constrained_columns') or [])
                for fk in inspector.get_foreign_keys('character_skills')
            }
            if ('skill_id',) not in existing_fks:
                op.create_foreign_key(
                    'fk_character_skills_skill_id', 'character_skills', 'skills',
                    ['skill_id'], ['id'], ondelete='CASCADE',
                )

    # Refresh inspector for the next steps
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # ----------------------------------------------------------------
    # 2b. Add the four base scalar columns to `skills` and backfill
    #     from rank-1 rows of `skill_ranks` BEFORE the rank tables are dropped.
    #     Previously these columns lived on SkillRank; in the perk model they
    #     belong directly on the skill row. We must preserve rank-1 values of
    #     already-configured skills on prod deploy.
    # ----------------------------------------------------------------
    SCALAR_COLS = (
        ('cost_energy', '0'),
        ('cost_mana', '0'),
        ('cooldown', '0'),
        ('level_requirement', '1'),
    )

    if 'skills' in tables:
        # Add columns as nullable first so backfill can write freely.
        for col_name, _ in SCALAR_COLS:
            if not _has_column(inspector, 'skills', col_name):
                op.add_column(
                    'skills',
                    sa.Column(col_name, sa.Integer(), nullable=True),
                )
        # Refresh inspector after add_column
        inspector = sa.inspect(bind)
        tables = set(inspector.get_table_names())

        # Backfill from rank-1 (lowest rank_number per skill) while skill_ranks still exists.
        if 'skill_ranks' in tables:
            op.execute(
                """
                UPDATE skills s
                JOIN skill_ranks sr
                    ON sr.skill_id = s.id
                   AND sr.rank_number = (
                        SELECT MIN(rank_number)
                        FROM (SELECT skill_id, rank_number FROM skill_ranks) sr2
                        WHERE sr2.skill_id = s.id
                   )
                SET s.cost_energy      = COALESCE(sr.cost_energy, 0),
                    s.cost_mana        = COALESCE(sr.cost_mana, 0),
                    s.cooldown         = COALESCE(sr.cooldown, 0),
                    s.level_requirement = COALESCE(sr.level_requirement, 1)
                """
            )

        # Fill any still-NULL rows (skills without ranks) with type defaults,
        # then lock to NOT NULL with server_default matching the type.
        op.execute(
            """
            UPDATE skills
            SET cost_energy       = COALESCE(cost_energy, 0),
                cost_mana         = COALESCE(cost_mana, 0),
                cooldown          = COALESCE(cooldown, 0),
                level_requirement = COALESCE(level_requirement, 1)
            """
        )
        for col_name, default in SCALAR_COLS:
            op.alter_column(
                'skills', col_name,
                existing_type=sa.Integer(),
                nullable=False,
                server_default=default,
            )

    # Refresh inspector before next section
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # ----------------------------------------------------------------
    # 3. Create skill_base_damage / skill_base_effects and copy from rank-0 rows
    # ----------------------------------------------------------------
    if 'skill_base_damage' not in tables:
        op.create_table(
            'skill_base_damage',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('skill_id', sa.Integer(), nullable=False),
            sa.Column('damage_type', sa.String(50), nullable=False),
            sa.Column('amount', sa.Float(), nullable=False, server_default='0'),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('weapon_slot', sa.String(20), server_default='main_weapon'),
            sa.Column('target_side', sa.String(10), nullable=False, server_default='self'),
            sa.Column('chance', sa.Integer(), server_default='100'),
            sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_skill_base_damage_skill_id', 'skill_base_damage', ['skill_id'])

    if 'skill_base_effects' not in tables:
        op.create_table(
            'skill_base_effects',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('skill_id', sa.Integer(), nullable=False),
            sa.Column('target_side', sa.String(10), server_default='self'),
            sa.Column('effect_name', sa.String(50), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('chance', sa.Integer(), server_default='100'),
            sa.Column('duration', sa.Integer(), server_default='1'),
            sa.Column('magnitude', sa.Float(), server_default='0'),
            sa.Column('attribute_key', sa.String(50), nullable=True),
            sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_skill_base_effects_skill_id', 'skill_base_effects', ['skill_id'])

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # Copy base data from rank tables if they still exist (lowest rank_number per skill).
    if 'skill_rank_damage' in tables and 'skill_ranks' in tables:
        op.execute(
            """
            INSERT INTO skill_base_damage
                (skill_id, damage_type, amount, description, weapon_slot, target_side, chance)
            SELECT sr.skill_id, srd.damage_type, srd.amount, srd.description,
                   srd.weapon_slot, srd.target_side, srd.chance
            FROM skill_rank_damage srd
            JOIN skill_ranks sr ON srd.skill_rank_id = sr.id
            JOIN (
                SELECT skill_id, MIN(rank_number) AS min_rank
                FROM skill_ranks
                GROUP BY skill_id
            ) base ON base.skill_id = sr.skill_id AND base.min_rank = sr.rank_number
            """
        )
    if 'skill_rank_effects' in tables and 'skill_ranks' in tables:
        op.execute(
            """
            INSERT INTO skill_base_effects
                (skill_id, target_side, effect_name, description, chance, duration, magnitude, attribute_key)
            SELECT sr.skill_id, sre.target_side, sre.effect_name, sre.description,
                   sre.chance, sre.duration, sre.magnitude, sre.attribute_key
            FROM skill_rank_effects sre
            JOIN skill_ranks sr ON sre.skill_rank_id = sr.id
            JOIN (
                SELECT skill_id, MIN(rank_number) AS min_rank
                FROM skill_ranks
                GROUP BY skill_id
            ) base ON base.skill_id = sr.skill_id AND base.min_rank = sr.rank_number
            """
        )

    # ----------------------------------------------------------------
    # 4. Drop rank tables
    # ----------------------------------------------------------------
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if 'skill_rank_effects' in tables:
        op.drop_table('skill_rank_effects')
    if 'skill_rank_damage' in tables:
        op.drop_table('skill_rank_damage')
    if 'skill_ranks' in tables:
        # Drop self-referential FKs first
        inspector2 = sa.inspect(bind)
        for fk in inspector2.get_foreign_keys('skill_ranks'):
            if fk.get('referred_table') == 'skill_ranks' and fk.get('name'):
                op.drop_constraint(fk['name'], 'skill_ranks', type_='foreignkey')
        op.drop_table('skill_ranks')

    # ----------------------------------------------------------------
    # 5. Create perk tables
    # ----------------------------------------------------------------
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if 'skill_perks' not in tables:
        op.create_table(
            'skill_perks',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('skill_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(120), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('perk_image', sa.String(255), nullable=True),
            sa.Column('delta_cost_energy', sa.Integer(), nullable=True),
            sa.Column('delta_cost_mana', sa.Integer(), nullable=True),
            sa.Column('delta_cooldown', sa.Integer(), nullable=True),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_skill_perks_skill_id', 'skill_perks', ['skill_id'])

    if 'skill_perk_damage' not in tables:
        op.create_table(
            'skill_perk_damage',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('skill_perk_id', sa.Integer(), nullable=False),
            sa.Column('damage_type', sa.String(50), nullable=False),
            sa.Column('amount', sa.Float(), nullable=False, server_default='0'),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('weapon_slot', sa.String(20), server_default='main_weapon'),
            sa.Column('target_side', sa.String(10), nullable=False, server_default='self'),
            sa.Column('chance', sa.Integer(), server_default='100'),
            sa.ForeignKeyConstraint(['skill_perk_id'], ['skill_perks.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_skill_perk_damage_perk', 'skill_perk_damage', ['skill_perk_id'])

    if 'skill_perk_effects' not in tables:
        op.create_table(
            'skill_perk_effects',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('skill_perk_id', sa.Integer(), nullable=False),
            sa.Column('target_side', sa.String(10), server_default='self'),
            sa.Column('effect_name', sa.String(50), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('chance', sa.Integer(), server_default='100'),
            sa.Column('duration', sa.Integer(), server_default='1'),
            sa.Column('magnitude', sa.Float(), server_default='0'),
            sa.Column('attribute_key', sa.String(50), nullable=True),
            sa.ForeignKeyConstraint(['skill_perk_id'], ['skill_perks.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_skill_perk_effects_perk', 'skill_perk_effects', ['skill_perk_id'])

    if 'character_skill_perks' not in tables:
        op.create_table(
            'character_skill_perks',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('character_skill_id', sa.Integer(), nullable=False),
            sa.Column('skill_perk_id', sa.Integer(), nullable=False),
            sa.Column('selected_at', sa.DateTime(), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['character_skill_id'], ['character_skills.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['skill_perk_id'], ['skill_perks.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('character_skill_id', 'skill_perk_id', name='uq_char_skill_perk'),
        )
        op.create_index('ix_character_skill_perks_perk', 'character_skill_perks', ['skill_perk_id'])


def downgrade() -> None:
    # Lossy. Brief accepts test-data loss.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for t in ('character_skill_perks', 'skill_perk_effects', 'skill_perk_damage',
              'skill_perks', 'skill_base_effects', 'skill_base_damage'):
        if t in tables:
            op.drop_table(t)
