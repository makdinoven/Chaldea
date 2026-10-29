# battle-pass-service (port 8012)

Seasons of the battle pass: levels with free/premium rewards, weekly missions, player progress.
Async SQLAlchemy (aiomysql), Alembic (auto-migration at start). Code: `services/battle-pass-service/app/`.

## Tables (owned)
`bp_seasons`, `bp_levels`, `bp_rewards`, `bp_missions`, `bp_user_progress`, `bp_user_rewards`
(unique `uq_user_level_track` = one claim per user/level/track), `bp_user_mission_progress`,
`bp_location_visits`, `bp_user_snapshots`.

## Tables read (owned by other services, raw SQL)
`characters`, `character_cumulative_stats`, `posts`, and the world-economy ledger of character-service
(`econ_accounts`, `econ_operations`, `econ_postings`, migration 027 — see `character-service.md` → «Economy ledger»).

## Endpoints (summary)
- Public/auth: `GET /battle-pass/seasons/current`, `GET /battle-pass/me/progress`, `GET /battle-pass/me/missions`,
  mission complete, `POST /battle-pass/me/rewards/claim`, `POST /battle-pass/me/premium/activate`.
- Admin (`/battle-pass/admin/...`): seasons CRUD, levels/rewards bulk PUT, missions bulk PUT.

## Reward delivery (outgoing HTTP, `X-Internal-Token`)
| Reward type | Call |
|---|---|
| `gold`, `xp` | character-service `POST /characters/{id}/add_rewards` |
| `item` | inventory-service `POST /inventory/internal/characters/{id}/items` |
| `diamonds` | user-service `POST /users/internal/{uid}/diamonds/add` |
| `frame`, `chat_background` | user-service `POST /users/internal/{uid}/cosmetics/unlock` |

### Gold/XP rewards and the economy ledger (FEAT-181)
`_deliver_gold_xp` sends `{xp, gold, xp_source: "character_xp_pass_bonus", gold_op_type: "battle_pass_reward",
payer: "world", idempotency_key}`. Gold is paid by the world account «Казна Скитальцев» (a season reward has no
natural location). The key is `battle_pass_reward:u:{user_id}:l:{level_id}:{track}` (`crud.reward_idempotency_key`)
— the same identity as the claim's unique constraint, so a retried or concurrent double claim pays once:
character-service answers `duplicate=true` and adds **neither XP nor gold**. Delivery happens before the
`bp_user_rewards` row is committed; on HTTP failure the error is raised and no claim is recorded.

## Mission progress
`kill_mobs` (cumulative stats delta vs snapshot), `write_posts`, `level_up` (delta vs snapshot), `visit_locations`,
`earn_gold`, `spend_gold`; `quest_complete`, `dungeon_run`, `resource_gather` are stubs (always 0).

**Gold missions (FEAT-181):** read the ledger, not `gold_transactions` (frozen):
- `earn_gold` = `SUM(econ_postings.amount)` where `to_account_id` is an `econ_accounts` row with
  `kind='character'` and `ref_id` ∈ the user's characters;
- `spend_gold` = same with `from_account_id`;
- both: `econ_postings.created_at >= season.start_date` and `econ_operations.op_type <> 'genesis'`.

Type-agnostic like before (trades, auction refunds count as earned; bids, purchases as spent). Old
`gold_transactions` rows are not merged — progress of these two mission types in the season running at the FEAT-181
deploy restarted from zero (accepted, Q6).
