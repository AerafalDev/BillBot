from common_pb2 import SpellModifierType

from DBDofusUnity.datas.protos.non_obf.game.common_pb2 import SpellModifier
from DBDofusUnity.datas.protos.non_obf.game.spell_pb2 import SpellItem
from DBDofusUnity.dofus_unity_reader.data_center.data_reader import DataReader
from DBDofusUnity.dofus_unity_reader.game_constants.characteristic import EffectElement
from DBDofusUnity.dofus_unity_reader.grid.map_point import MapPoint
from DBDofusUnity.dofus_unity_reader.models.datas.spell_levels_root import (
    Effect,
    SpellLevelsRootItem,
)
from DBDofusUnity.dofus_unity_reader.models.datas.zone_descr import ZoneDescr
from src.core.engine.fights.effect import (
    can_target_enemy,
    is_fixed_neutral_damage_effect,
    is_heal_effect,
    is_instant_kill_effect,
    is_ap_mp_loss_effect,
    is_erosion_effect,
    is_push_effect,
    is_state_effect,
    resolve_effect_damage_element,
)
from src.core.engine.fights.zones.cross import Cross
from src.core.engine.fights.zones.lozenge import Lozenge

ModifierMap = dict[tuple[int, SpellModifierType], SpellModifier]


def get_max_range_spell(
    stat_po: int,
    spell_lvl: SpellLevelsRootItem,
    modifier_range_max: SpellModifier | None,
    modifier_range_min: SpellModifier | None = None,
    modifier_range_boost: SpellModifier | None = None,
) -> int:
    range = spell_lvl.range + (modifier_range_max.context if modifier_range_max else 0)
    min_range = get_min_range_spell(spell_lvl, modifier_range_min)

    if (spell_lvl.m_flags & 64) != 0 or bool(
        modifier_range_boost and modifier_range_boost.context > 0
    ):
        range += stat_po

    return max(range, min_range)


def get_min_range_spell(spell_lvl: SpellLevelsRootItem, modifier_range_min: SpellModifier | None) -> int:
    return max(spell_lvl.minRange + (modifier_range_min.context if modifier_range_min else 0), 0)


def get_ap_cost_spell(spell_lvl: SpellLevelsRootItem, modifier_ap_cost: SpellModifier | None) -> int:
    return max(spell_lvl.apCost - (modifier_ap_cost.context if modifier_ap_cost else 0), 0)


def get_spell_max_cast_per_turn(
    spell_lvl: SpellLevelsRootItem, modifier_max_cast_per_turn: SpellModifier | None
):
    return spell_lvl.maxCastPerTurn + (
        modifier_max_cast_per_turn.context if modifier_max_cast_per_turn else 0
    )


def get_spell_max_cast_per_target(
    spell_lvl: SpellLevelsRootItem, modifier_max_cast_per_target: SpellModifier | None
):
    return spell_lvl.maxCastPerTarget + (
        modifier_max_cast_per_target.context if modifier_max_cast_per_target else 0
    )


def is_spell_cast_in_line(spell_lvl: SpellLevelsRootItem, modifier_cast_line: SpellModifier | None) -> bool:
    return (spell_lvl.m_flags & 1) != 0 or bool(modifier_cast_line and modifier_cast_line.context > 0)


def is_spell_cast_in_diagonal(spell_lvl: SpellLevelsRootItem) -> bool:
    if (spell_lvl.m_flags & 2) != 0:
        return True
    return False


def does_spell_need_free_cell(
    spell_lvl: SpellLevelsRootItem, modifier_free_cell: SpellModifier | None = None
) -> bool:
    return (spell_lvl.m_flags & 8) != 0 or bool(modifier_free_cell and modifier_free_cell.context > 0)


def does_spell_need_taken_cell(
    spell_lvl: SpellLevelsRootItem, modifier_occupied_cell: SpellModifier | None = None
) -> bool:
    return (spell_lvl.m_flags & 16) != 0 or bool(
        modifier_occupied_cell and modifier_occupied_cell.context > 0
    )


def does_spell_need_visible_entity(
    spell_lvl: SpellLevelsRootItem, modifier_visible_target: SpellModifier | None = None
) -> bool:
    return (spell_lvl.m_flags & 32) != 0 or bool(
        modifier_visible_target and modifier_visible_target.context > 0
    )


def does_spell_need_test_los(
    spell_lvl: SpellLevelsRootItem, modifier_los: SpellModifier | None = None
) -> bool:
    return (spell_lvl.m_flags & 4) != 0 and not bool(modifier_los and modifier_los.context > 0)


def get_possible_mp_spell(
    origin: MapPoint,
    spell_lvl: SpellLevelsRootItem,
    stat_po: int,
    modifier_range_min: SpellModifier | None,
    modifier_range_max: SpellModifier | None,
    modifier_cast_line: SpellModifier | None,
    modifier_range_boost: SpellModifier | None = None,
) -> set[MapPoint]:
    min_range = get_min_range_spell(spell_lvl, modifier_range_min)
    max_range = get_max_range_spell(
        stat_po,
        spell_lvl,
        modifier_range_max,
        modifier_range_min,
        modifier_range_boost,
    )

    if is_spell_cast_in_line(spell_lvl, modifier_cast_line):
        cross = Cross(shape=None, alternative_size=min_range, size=max_range)
        possible_mps = cross.get_mps(mp=origin, direction=None)
    elif is_spell_cast_in_diagonal(spell_lvl):
        cross = Cross(
            shape=None,
            alternative_size=min_range,
            size=max_range,
            is_all_directions=True,
            is_diagonal=True,
        )
        possible_mps = cross.get_mps(mp=origin, direction=None)
    else:
        lozenge = Lozenge(alternative_size=min_range, size=max_range)
        possible_mps = lozenge.get_mps(origin, direction=None)

    return possible_mps


def get_damage_spells(
    spells: list[SpellItem],
    primary_elem: EffectElement,
    *,
    include_push_effects: bool = False,
    include_tactical_effects: bool = False,
) -> list[tuple[SpellLevelsRootItem, Effect]]:
    spell_levels: list[tuple[SpellLevelsRootItem, Effect]] = []
    for spell in spells:
        if not spell.spell_id:
            continue
        spell_lvl = DataReader().spell_lvl_by_spell_id[spell.spell_id][spell.spell_level - 1]

        seen_zones: list[ZoneDescr] = []
        for effect in spell_lvl.effects:
            data_effect = DataReader().effect_by_id[effect.effectId]
            is_push = include_push_effects and is_push_effect(effect)
            is_kill = include_tactical_effects and is_instant_kill_effect(effect)
            is_point_loss = include_tactical_effects and is_ap_mp_loss_effect(effect)
            is_erosion = include_tactical_effects and is_erosion_effect(effect)
            is_state = include_tactical_effects and is_state_effect(effect)
            if (
                data_effect.characteristicOperator != ""
                and not is_fixed_neutral_damage_effect(effect)
                and not is_push
                and not is_kill
                and not is_point_loss
                and not is_erosion
                and not is_state
            ):
                continue
            if is_heal_effect(effect):
                continue
            if not can_target_enemy(effect):
                continue
            has_damage = resolve_effect_damage_element(effect, primary_elem) is not None
            if has_damage or is_push or is_kill or is_point_loss or is_erosion or is_state:
                if effect.zoneDescr in seen_zones:
                    continue
                spell_levels.append((spell_lvl, effect))
                seen_zones.append(effect.zoneDescr)

    return spell_levels


def spell_modifier_value(
    spell_id: int, modifier_type: SpellModifierType, modifiers: ModifierMap | None
) -> int:
    if not modifiers:
        return 0
    modifier = modifiers.get((spell_id, modifier_type))

    return modifier.context if modifier else 0
