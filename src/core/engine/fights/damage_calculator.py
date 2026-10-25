import math
from collections.abc import Mapping
from dataclasses import dataclass

from DBDofusUnity.datas.protos.non_obf.game.common_pb2 import (
    CharacterCharacteristic,
    SpellModifierType,
)
from DBDofusUnity.dofus_unity_reader.game_constants.characteristic import (
    CharacteristicEnum,
    EffectElement,
)
from DBDofusUnity.dofus_unity_reader.models.datas.monsters_root import MonsterGrade
from DBDofusUnity.dofus_unity_reader.models.datas.spell_levels_root import (
    Effect,
    SpellLevelsRootItem,
)

from src.core.engine.fights.effect import (
    base_roll,
    get_critical_effect,
    is_fixed_neutral_damage_effect,
    resolve_effect_damage_element,
)
from src.core.engine.fights.spell import ModifierMap, spell_modifier_value
from src.core.engine.fights.stats.characteristic import get_stat_by_id


@dataclass(frozen=True)
class _ElementInfo:
    scaling_stat: CharacteristicEnum
    flat_damage_bonus: CharacteristicEnum


ELEMENT_INFO_BY_ID: dict[int, _ElementInfo] = {
    EffectElement.NEUTRAL_ELEMENT: _ElementInfo(
        CharacteristicEnum.STRENGTH, CharacteristicEnum.NEUTRAL_DAMAGE_BONUS
    ),
    EffectElement.STRENGTH: _ElementInfo(CharacteristicEnum.STRENGTH, CharacteristicEnum.EARTH_DAMAGE_BONUS),
    EffectElement.INTELLIGENCE: _ElementInfo(
        CharacteristicEnum.INTELLIGENCE, CharacteristicEnum.FIRE_DAMAGE_BONUS
    ),
    EffectElement.CHANCE: _ElementInfo(CharacteristicEnum.CHANCE, CharacteristicEnum.WATER_DAMAGE_BONUS),
    EffectElement.AGILITY: _ElementInfo(CharacteristicEnum.AGILITY, CharacteristicEnum.AIR_DAMAGE_BONUS),
}

CASTER_CURRENT_LIFE_DAMAGE_ACTION_IDS = frozenset({85, 86, 87, 88, 89})
CASTER_MISSING_LIFE_DAMAGE_ACTION_IDS = frozenset({278, 279})
CASTER_MIDLIFE_DAMAGE_ACTION_IDS = frozenset({672})
TARGET_CURRENT_LIFE_DAMAGE_ACTION_IDS = frozenset({1067, 1068, 1069, 1070, 1071})
TARGET_MISSING_LIFE_DAMAGE_ACTION_IDS = frozenset({1092, 1093, 1094, 1095, 1096})


def _multiplier_factor(characteristic_by_id: dict[int, CharacterCharacteristic], stat_id: int) -> float:
    raw = get_stat_by_id(characteristic_by_id.get(stat_id))
    return (raw if raw > 0 else 100) / 100


RESIST_CHARACTERISTIC_BY_ELEMENT: dict[int, CharacteristicEnum] = {
    EffectElement.STRENGTH: CharacteristicEnum.EARTH_ELEMENT_RESIST_PERCENT,
    EffectElement.INTELLIGENCE: CharacteristicEnum.FIRE_ELEMENT_RESIST_PERCENT,
    EffectElement.CHANCE: CharacteristicEnum.WATER_ELEMENT_RESIST_PERCENT,
    EffectElement.AGILITY: CharacteristicEnum.AIR_ELEMENT_RESIST_PERCENT,
    EffectElement.NEUTRAL_ELEMENT: CharacteristicEnum.NEUTRAL_ELEMENT_RESIST_PERCENT,
}


def _monster_resist_percent(
    element_id: int,
    monster_grade: MonsterGrade | None,
    target_characteristic_by_id: Mapping[int, CharacterCharacteristic] | None,
) -> int:
    """Prefer combat snapshot resistances and fall back when a row is absent."""
    characteristic_id = RESIST_CHARACTERISTIC_BY_ELEMENT[element_id]
    if target_characteristic_by_id is not None and characteristic_id in target_characteristic_by_id:
        return get_stat_by_id(target_characteristic_by_id[characteristic_id])
    if monster_grade is None:
        return 0
    bonus = monster_grade.bonusCharacteristics
    match element_id:
        case EffectElement.STRENGTH:
            return monster_grade.earthResistance + bonus.earthResistance
        case EffectElement.INTELLIGENCE:
            return monster_grade.fireResistance + bonus.fireResistance
        case EffectElement.CHANCE:
            return monster_grade.waterResistance + bonus.waterResistance
        case EffectElement.AGILITY:
            return monster_grade.airResistance + bonus.airResistance
        case _:
            return monster_grade.neutralResistance + bonus.neutralResistance


def _percent_factor(
    element_id: int,
    characteristic_by_id: dict[int, CharacterCharacteristic],
    spell_id: int,
    modifiers: ModifierMap | None,
) -> float:
    info = ELEMENT_INFO_BY_ID[element_id]
    bonus = (
        get_stat_by_id(characteristic_by_id.get(info.scaling_stat))
        + get_stat_by_id(characteristic_by_id.get(CharacteristicEnum.POWER))
        + get_stat_by_id(characteristic_by_id.get(CharacteristicEnum.DAMAGES_PERCENT_SPELL))
        + spell_modifier_value(spell_id, SpellModifierType.DAMAGE, modifiers)
    )
    return (100 + bonus) / 100


def _flat_bonus(
    element_id: int,
    characteristic_by_id: dict[int, CharacterCharacteristic],
    is_critical: bool,
) -> int:
    info = ELEMENT_INFO_BY_ID[element_id]
    flat = get_stat_by_id(characteristic_by_id.get(CharacteristicEnum.ALL_DAMAGES_BONUS)) + get_stat_by_id(
        characteristic_by_id.get(info.flat_damage_bonus)
    )
    if is_critical:
        flat += get_stat_by_id(characteristic_by_id.get(CharacteristicEnum.CRITICAL_DAMAGE_BONUS))
    return flat


def _dealt_multipliers(characteristic_by_id: dict[int, CharacterCharacteristic], is_melee: bool) -> float:
    melee_or_distance = (
        CharacteristicEnum.DEALT_DAMAGE_MULTIPLIER_MELEE
        if is_melee
        else CharacteristicEnum.DEALT_DAMAGE_MULTIPLIER_DISTANCE
    )
    return (
        _multiplier_factor(characteristic_by_id, CharacteristicEnum.DEALT_DAMAGE_MULTIPLIER)
        * _multiplier_factor(characteristic_by_id, melee_or_distance)
        * _multiplier_factor(characteristic_by_id, CharacteristicEnum.DEALT_DAMAGE_MULTIPLIER_SPELLS)
    )


def _crit_probability(
    spell_lvl: SpellLevelsRootItem,
    characteristic_by_id: dict[int, CharacterCharacteristic],
    modifiers: ModifierMap | None,
) -> float:
    if spell_lvl.criticalHitProbability <= 0 or not spell_lvl.criticalEffect:
        return 0.0
    crit_chance = spell_lvl.criticalHitProbability + get_stat_by_id(
        characteristic_by_id.get(CharacteristicEnum.CRITICAL_HIT)
    ) + spell_modifier_value(spell_lvl.spellId, SpellModifierType.CRITICAL_HIT_BONUS, modifiers)
    return min(max(crit_chance, 0), 100) / 100


def _damage_for_effect(
    effect: Effect,
    element_id: int,
    monster_grade: MonsterGrade | None,
    characteristic_by_id: dict[int, CharacterCharacteristic],
    is_critical: bool,
    modifiers: ModifierMap | None,
    caster_life_point: int,
    caster_max_life_point: int,
    target_life_point: int,
    target_max_life_point: int,
    target_characteristic_by_id: Mapping[int, CharacterCharacteristic] | None,
) -> float:
    if is_fixed_neutral_damage_effect(effect):
        raw = base_roll(effect)
        if raw <= 0:
            return 0.0
        raw *= 1 - _monster_resist_percent(
            element_id, monster_grade, target_characteristic_by_id
        ) / 100
        return max(raw, 0.0)

    base = _effect_base_damage(
        effect,
        caster_life_point,
        caster_max_life_point,
        target_life_point,
        target_max_life_point,
    ) + spell_modifier_value(effect.spellId, SpellModifierType.BASE_DAMAGE, modifiers)
    raw = base * _percent_factor(element_id, characteristic_by_id, effect.spellId, modifiers) + _flat_bonus(
        element_id, characteristic_by_id, is_critical
    )
    if raw <= 0:
        return 0.0

    raw *= 1 - _monster_resist_percent(
        element_id, monster_grade, target_characteristic_by_id
    ) / 100
    return max(raw, 0.0)


def _effect_base_damage(
    effect: Effect,
    caster_life_point: int,
    caster_max_life_point: int,
    target_life_point: int,
    target_max_life_point: int,
) -> float:
    base = base_roll(effect)
    if effect.effectId in CASTER_CURRENT_LIFE_DAMAGE_ACTION_IDS:
        return base * caster_life_point / 100
    if effect.effectId in CASTER_MISSING_LIFE_DAMAGE_ACTION_IDS:
        return base * max(caster_max_life_point - caster_life_point, 0) / 100
    if effect.effectId in CASTER_MIDLIFE_DAMAGE_ACTION_IDS:
        if caster_max_life_point <= 0:
            return 0.0
        distance_from_half = min(abs(100 * caster_life_point / caster_max_life_point - 50), 50)
        midlife_index = int(distance_from_half)
        midlife_percent = ((1 + math.cos(2 * math.pi * midlife_index * 0.01)) * 0.5) ** 2 / 4
        return base * caster_max_life_point * midlife_percent / 100
    if effect.effectId in TARGET_CURRENT_LIFE_DAMAGE_ACTION_IDS:
        return base * target_life_point / 100
    if effect.effectId in TARGET_MISSING_LIFE_DAMAGE_ACTION_IDS:
        return base * max(target_max_life_point - target_life_point, 0) / 100
    return base


@dataclass
class DamageCalculator:
    def get_damage_effect(
        self,
        effect: Effect,
        spell_lvl: SpellLevelsRootItem,
        monster_grade: MonsterGrade | None,
        characteristic_by_id: dict[int, CharacterCharacteristic],
        is_melee: bool,
        primary_elem: EffectElement,
        modifiers: ModifierMap | None = None,
        *,
        caster_life_point: int = 0,
        caster_max_life_point: int = 0,
        target_life_point: int = 0,
        target_max_life_point: int = 0,
        target_characteristic_by_id: Mapping[int, CharacterCharacteristic] | None = None,
    ) -> int:
        """Predict monster damage; unknown resistance is treated as zero and special redirections are excluded."""
        element_id = resolve_effect_damage_element(effect, primary_elem)
        if element_id is None:
            return 0

        damage_multiplier = _dealt_multipliers(characteristic_by_id, is_melee)
        normal_damage = _damage_for_effect(
            effect,
            element_id,
            monster_grade,
            characteristic_by_id,
            is_critical=False,
            modifiers=modifiers,
            caster_life_point=caster_life_point,
            caster_max_life_point=caster_max_life_point,
            target_life_point=target_life_point,
            target_max_life_point=target_max_life_point,
            target_characteristic_by_id=target_characteristic_by_id,
        )

        normal_damage_multiplier = 1.0 if is_fixed_neutral_damage_effect(effect) else damage_multiplier
        crit_probability = _crit_probability(spell_lvl, characteristic_by_id, modifiers)
        if crit_probability <= 0:
            return math.floor(normal_damage * normal_damage_multiplier)

        critical_effect = get_critical_effect(spell_lvl, effect)
        crit_damage = _damage_for_effect(
            critical_effect,
            element_id,
            monster_grade,
            characteristic_by_id,
            is_critical=True,
            modifiers=modifiers,
            caster_life_point=caster_life_point,
            caster_max_life_point=caster_max_life_point,
            target_life_point=target_life_point,
            target_max_life_point=target_max_life_point,
            target_characteristic_by_id=target_characteristic_by_id,
        )
        critical_damage_multiplier = (
            1.0 if is_fixed_neutral_damage_effect(critical_effect) else damage_multiplier
        )
        expected = (
            (1 - crit_probability) * normal_damage * normal_damage_multiplier
            + crit_probability * crit_damage * critical_damage_multiplier
        )
        return math.floor(expected)
