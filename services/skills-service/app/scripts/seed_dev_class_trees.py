"""
Dev-only helper: fill in placeholder class skill trees so the combined skill
wheel has something to draw locally.

Production already has authored trees, so this script NEVER touches a class that
already has a ``tree_type='class'`` tree — it only creates what is missing. Pass
``--replace`` to wipe and regenerate a class's tree; that is destructive and is
meant for a local database only.

Run it inside the container:

    docker compose exec skills-service python scripts/seed_dev_class_trees.py
    docker compose exec skills-service python scripts/seed_dev_class_trees.py --replace 2 3

It is deliberately not an Alembic migration and not part of the seed SQL, so it
can never run on its own against prod.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select  # noqa: E402

import models  # noqa: E402
from database import async_session, engine  # noqa: E402
from subclasses import SUBCLASSES  # noqa: E402

CLASS_NAMES = {1: "Воин", 2: "Плут", 3: "Маг"}

# (level_ring, how many nodes on that ring) — a fan that widens then narrows.
RING_SHAPE = [(1, 1), (5, 2), (10, 3), (15, 4), (20, 5), (25, 4), (30, 3)]

# Admin-editor coordinate grid. The player view rotates whole trees into their
# sector, so only the shape here matters, not the absolute origin.
COLUMN_SPACING = 150
RING_SPACING = 160
ORIGIN_X = 600
ORIGIN_Y = 1200


def _node_positions() -> list[list[tuple[int, float, float, int]]]:
    """Returns, per ring, a list of (level_ring, x, y, index_on_ring)."""
    rings = []
    for ring_index, (level_ring, count) in enumerate(RING_SHAPE):
        row = []
        for i in range(count):
            x = ORIGIN_X + (i - (count - 1) / 2) * COLUMN_SPACING
            y = ORIGIN_Y - ring_index * RING_SPACING
            row.append((level_ring, x, y, i))
        rings.append(row)
    return rings


async def _seed_class(session, class_id: int, replace: bool) -> str:
    existing = (
        await session.execute(
            select(models.ClassSkillTree).where(
                models.ClassSkillTree.class_id == class_id,
                models.ClassSkillTree.tree_type == "class",
            )
        )
    ).scalar_one_or_none()

    if existing and not replace:
        return f"класс {class_id}: дерево уже есть (id={existing.id}), пропускаю"

    if existing:
        # Nodes and connections cascade from the tree, but progress rows point at
        # node ids directly, so clear those first.
        node_ids = (
            await session.execute(
                select(models.TreeNode.id).where(models.TreeNode.tree_id == existing.id)
            )
        ).scalars().all()
        if node_ids:
            await session.execute(
                delete(models.CharacterTreeProgress).where(
                    models.CharacterTreeProgress.node_id.in_(node_ids)
                )
            )
        await session.delete(existing)
        await session.flush()

    class_name = CLASS_NAMES.get(class_id, f"Класс {class_id}")
    tree = models.ClassSkillTree(
        class_id=class_id,
        name=f"Древо {class_name.lower()}а" if class_id != 3 else "Древо мага",
        description="Заготовка для настройки. Замените узлы в админке.",
        tree_type="class",
    )
    session.add(tree)
    await session.flush()

    subclass_keys = [s.key for s in SUBCLASSES if s.class_id == class_id]
    subclass_names = {s.key: s.name for s in SUBCLASSES if s.class_id == class_id}

    rings = _node_positions()
    created: list[list[models.TreeNode]] = []

    for ring_index, row in enumerate(rings):
        is_first = ring_index == 0
        is_last = ring_index == len(rings) - 1
        ring_nodes = []
        for level_ring, x, y, i in row:
            if is_first:
                node_type, subclass_key = "root", None
                name = f"{class_name} — начало"
            elif is_last and i < len(subclass_keys):
                node_type, subclass_key = "subclass_choice", subclass_keys[i]
                name = subclass_names[subclass_key]
            else:
                node_type, subclass_key = "regular", None
                name = f"{class_name} {level_ring}-{i + 1}"

            node = models.TreeNode(
                tree_id=tree.id,
                level_ring=level_ring,
                position_x=x,
                position_y=y,
                name=name,
                description=None,
                node_type=node_type,
                subclass_key=subclass_key,
                sort_order=i,
            )
            session.add(node)
            ring_nodes.append(node)
        await session.flush()
        created.append(ring_nodes)

    # Each node hangs off the closest node on the ring below it, which keeps the
    # fan connected without crossing lines.
    connection_count = 0
    for ring_index in range(1, len(created)):
        for node in created[ring_index]:
            parent = min(
                created[ring_index - 1],
                key=lambda p: abs(p.position_x - node.position_x),
            )
            session.add(
                models.TreeNodeConnection(
                    tree_id=tree.id,
                    from_node_id=parent.id,
                    to_node_id=node.id,
                )
            )
            connection_count += 1

    await session.flush()
    node_total = sum(len(r) for r in created)
    return (
        f"класс {class_id}: создано дерево id={tree.id}, "
        f"узлов {node_total}, связей {connection_count}"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "classes", nargs="*", type=int, default=list(CLASS_NAMES),
        help="class ids to seed (default: 1 2 3)",
    )
    parser.add_argument(
        "--replace", action="store_true",
        help="DESTRUCTIVE: drop the class's existing tree and its progress first",
    )
    args = parser.parse_args()

    async with async_session() as session:
        for class_id in args.classes:
            print(await _seed_class(session, class_id, args.replace))
        await session.commit()
    # Without this aiomysql finalises its connections after the loop is gone and
    # prints a "Event loop is closed" traceback over the script's output.
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
