"""Deduplicate location transitions and make them unique per direction.

The admin location editor re-saved arrow transitions (is_auto_arrow=1) as
manual rows, so a pair of locations ended up with two or three rows in one
direction, often with different stamina costs; the manual copy also survived
when the arrow path was deleted.

* Manual rows that duplicate an arrow row of the same direction are deleted
  (the arrow is the source of truth for its cost).
* Any remaining duplicates of one direction keep only the newest row.
* arrow_neighbors gets the same clean-up per (location_id, arrow_id).
* Arrow rows get the cost of their arrow paths back (sum of both sides).
* Unique keys stop it from happening again.

Downgrade drops the unique keys (the deleted duplicates are not restored).

Revision ID: 059_location_neighbor_unique
Revises: 058_quest_faction_vouchers
Create Date: 2026-11-15

"""
from alembic import op
from sqlalchemy import inspect

revision = '059_location_neighbor_unique'
down_revision = '058_quest_faction_vouchers'
branch_labels = None
depends_on = None

NEIGHBORS = 'LocationNeighbors'
ARROW_NEIGHBORS = 'arrow_neighbors'
NEIGHBOR_UQ = 'uq_location_neighbor_pair'
ARROW_UQ = 'uq_arrow_neighbor_location'
NEIGHBOR_LOCATION_INDEX = 'ix_location_neighbors_location'


def _index_names(bind, table) -> set:
    insp = inspect(bind)
    names = {i['name'] for i in insp.get_indexes(table)}
    names |= {u['name'] for u in insp.get_unique_constraints(table)}
    return names


def upgrade() -> None:
    bind = op.get_bind()

    # 1) A manual row next to an arrow row of the same direction is a copy.
    op.execute(
        f"DELETE m FROM `{NEIGHBORS}` m "
        f"JOIN `{NEIGHBORS}` a ON a.location_id = m.location_id "
        f"AND a.neighbor_id = m.neighbor_id AND a.is_auto_arrow = 1 "
        f"WHERE m.is_auto_arrow = 0"
    )
    # 2) Whatever duplicates remain: keep the newest row of each direction.
    op.execute(
        f"DELETE x FROM `{NEIGHBORS}` x "
        f"JOIN `{NEIGHBORS}` y ON y.location_id = x.location_id "
        f"AND y.neighbor_id = x.neighbor_id AND y.id > x.id"
    )
    op.execute(
        f"DELETE x FROM `{ARROW_NEIGHBORS}` x "
        f"JOIN `{ARROW_NEIGHBORS}` y ON y.location_id = x.location_id "
        f"AND y.arrow_id = x.arrow_id AND y.id > x.id"
    )
    # 3) Arrow rows take the cost of their arrow paths, as the next resync of
    #    the arrow would write anyway (some were edited by hand to stale values).
    op.execute(
        f"UPDATE `{NEIGHBORS}` ln JOIN ("
        f"  SELECT an1.location_id AS l1, an2.location_id AS l2, "
        f"         MIN(an1.energy_cost + an2.energy_cost) AS cost "
        f"  FROM `{ARROW_NEIGHBORS}` an1 "
        f"  JOIN region_transition_arrows a ON a.id = an1.arrow_id "
        f"  JOIN `{ARROW_NEIGHBORS}` an2 ON an2.arrow_id = a.paired_arrow_id "
        f"  GROUP BY an1.location_id, an2.location_id"
        f") x ON ln.location_id = x.l1 AND ln.neighbor_id = x.l2 "
        f"SET ln.energy_cost = x.cost WHERE ln.is_auto_arrow = 1"
    )

    if NEIGHBOR_UQ not in _index_names(bind, NEIGHBORS):
        op.create_unique_constraint(NEIGHBOR_UQ, NEIGHBORS, ['location_id', 'neighbor_id'])
    if ARROW_UQ not in _index_names(bind, ARROW_NEIGHBORS):
        op.create_unique_constraint(ARROW_UQ, ARROW_NEIGHBORS, ['location_id', 'arrow_id'])


def downgrade() -> None:
    bind = op.get_bind()

    names = _index_names(bind, NEIGHBORS)
    if NEIGHBOR_UQ in names:
        # The location_id FK may be using the unique key as its index; give it
        # a plain one first so MySQL lets the unique key go.
        if NEIGHBOR_LOCATION_INDEX not in names:
            op.create_index(NEIGHBOR_LOCATION_INDEX, NEIGHBORS, ['location_id'])
        op.drop_constraint(NEIGHBOR_UQ, NEIGHBORS, type_='unique')

    if ARROW_UQ in _index_names(bind, ARROW_NEIGHBORS):
        op.drop_constraint(ARROW_UQ, ARROW_NEIGHBORS, type_='unique')
