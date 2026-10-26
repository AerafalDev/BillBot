from dataclasses import dataclass

from DBDofusUnity.datas.protos.non_obf.game.common_pb2 import SpellModifier, SpellModifierType
from DBDofusUnity.dofus_unity_reader.models.datas.spell_levels_root import SpellLevelsRootItem

from src.core.engine.fights.spell import (
    get_ap_cost_spell,
    get_max_range_spell,
    get_min_range_spell,
    get_spell_max_cast_per_target,
    get_spell_max_cast_per_turn,
    does_spell_need_free_cell,
    does_spell_need_taken_cell,
    does_spell_need_test_los,
    does_spell_need_visible_entity,
    is_spell_cast_in_line,
)


@dataclass
class SpellModifiers:
    ap_cost: int
    heal_bonus: int
    max_cast_per_turn: int
    max_cast_per_target: int
    min_cast_interval: int
    range_min: int
    range_max: int
    cast_line: bool
    cast_test_los: bool
    needs_free_cell: bool
    needs_taken_cell: bool
    needs_visible_entity: bool

    @classmethod
    def from_spell(
        cls,
        stat_po: int,
        spell_lvl: SpellLevelsRootItem,
        modifiers_map: dict[tuple[int, SpellModifierType], SpellModifier],
    ) -> "SpellModifiers":
        spell_id = spell_lvl.spellId
        cast_interval_modifier = modifiers_map.get((spell_id, SpellModifierType.CAST_INTERVAL))
        return cls(
            ap_cost=get_ap_cost_spell(spell_lvl, modifiers_map.get((spell_id, SpellModifierType.AP_COST))),
            heal_bonus=(
                modifiers_map[(spell_id, SpellModifierType.HEAL_BONUS)].context
                if (spell_id, SpellModifierType.HEAL_BONUS) in modifiers_map
                else 0
            ),
            max_cast_per_turn=(
                get_spell_max_cast_per_turn(
                    spell_lvl,
                    modifiers_map.get((spell_id, SpellModifierType.MAX_CAST_PER_TURN)),
                )
            ),
            max_cast_per_target=(
                get_spell_max_cast_per_target(
                    spell_lvl,
                    modifiers_map.get((spell_id, SpellModifierType.MAX_CAST_PER_TARGET)),
                )
            ),
            range_min=get_min_range_spell(
                spell_lvl, modifiers_map.get((spell_id, SpellModifierType.RANGE_MIN))
            ),
            min_cast_interval=max(
                spell_lvl.minCastInterval
                - (cast_interval_modifier.context if cast_interval_modifier else 0),
                0,
            ),
            range_max=get_max_range_spell(
                stat_po,
                spell_lvl,
                modifiers_map.get((spell_id, SpellModifierType.RANGE_MAX)),
                modifiers_map.get((spell_id, SpellModifierType.RANGE_MIN)),
                modifiers_map.get((spell_id, SpellModifierType.RANGE)),
            ),
            cast_line=is_spell_cast_in_line(
                spell_lvl, modifiers_map.get((spell_id, SpellModifierType.CAST_LINE))
            ),
            cast_test_los=does_spell_need_test_los(
                spell_lvl, modifiers_map.get((spell_id, SpellModifierType.LOS))
            ),
            needs_free_cell=does_spell_need_free_cell(
                spell_lvl, modifiers_map.get((spell_id, SpellModifierType.FREE_CELL))
            ),
            needs_taken_cell=does_spell_need_taken_cell(
                spell_lvl, modifiers_map.get((spell_id, SpellModifierType.OCCUPIED_CELL))
            ),
            needs_visible_entity=does_spell_need_visible_entity(
                spell_lvl, modifiers_map.get((spell_id, SpellModifierType.VISIBLE_TARGET))
            ),
        )
