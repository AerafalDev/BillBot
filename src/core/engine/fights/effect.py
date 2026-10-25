
import re
from functools import cache

from DBDofusUnity.dofus_unity_reader.data_center.data_reader import DataReader
from DBDofusUnity.dofus_unity_reader.data_center.i18n import I18N
from DBDofusUnity.dofus_unity_reader.game_constants.characteristic import (
    CharacteristicEnum,
    EffectElement,
    TypeEffect,
)
from DBDofusUnity.dofus_unity_reader.game_constants.description import DescriptionEnum
from DBDofusUnity.dofus_unity_reader.models.datas.spell_levels_root import (
    Effect,
    SpellLevelsRootItem,
)


BEST_ELEMENT = 5
# ActionCharacterLifePointsLostNoBoost from the shared Dofus action IDs.
FIXED_NEUTRAL_DAMAGE_ACTION_ID = 144
INSTANT_KILL_ACTION_ID = 141
MOVEMENT_POINT_STEAL_ACTION_ID = 77
PUSH_ACTION_IDS: frozenset[int] = frozenset({5, 783, 1103})
ADD_STATE_ACTION_ID = 950
REMOVE_STATE_ACTION_ID = 951
EROSION_ACTION_ID = 776
RUNE_TRIGGER_ACTION_ID = 2023
RUNE_PLACEMENT_ACTION_ID = 2022


def _has_description(effect: Effect, description_ids: frozenset[int]) -> bool:
    return DataReader().effect_by_id[effect.effectId].descriptionId in description_ids


HEAL_DESCRIPTION_IDS: frozenset[int] = frozenset(
    {
        DescriptionEnum.HEAL_FLAT_LIFE,
        DescriptionEnum.HEAL_PERCENT_MAX_LIFE,
        DescriptionEnum.HEAL_FIXED,
        DescriptionEnum.HEAL_PLAIN,
        DescriptionEnum.HEAL_SINGLE,
        DescriptionEnum.HEAL_WATER,
        DescriptionEnum.HEAL_AIR,
        DescriptionEnum.HEAL_EARTH,
        DescriptionEnum.HEAL_NEUTRAL,
        DescriptionEnum.HEAL_BEST_ELEMENT,
        DescriptionEnum.HEAL_FIRE,
        DescriptionEnum.HEAL_ELEMENTAL,
    }
)


def is_heal_effect(effect: Effect) -> bool:
    """Heal categories overlap with conditional damage effects, so category alone is insufficient."""
    return _has_description(effect, HEAL_DESCRIPTION_IDS) or effect.effectId in {
        81,
        108,
        110,
        143,
        407,
        1109,
        2998,
        2999,
        3000,
        3001,
        3002,
    }


def is_fixed_neutral_damage_effect(effect: Effect) -> bool:
    return effect.effectId == FIXED_NEUTRAL_DAMAGE_ACTION_ID


def is_life_steal_effect(effect: Effect) -> bool:
    return effect.effectId in {91, 92, 93, 94, 95}


def is_instant_kill_effect(effect: Effect) -> bool:
    return effect.effectId == INSTANT_KILL_ACTION_ID


def is_state_effect(effect: Effect) -> bool:
    return effect.effectId in {ADD_STATE_ACTION_ID, REMOVE_STATE_ACTION_ID}


def is_state_removal_effect(effect: Effect) -> bool:
    return effect.effectId == REMOVE_STATE_ACTION_ID


def get_state_id(effect: Effect) -> int | None:
    if not is_state_effect(effect) or effect.value <= 0:
        return None
    return effect.value


def is_beneficial_self_state_effect(effect: Effect, active_state_ids: frozenset[int]) -> bool:
    state_id = get_state_id(effect)
    if state_id is None:
        return False
    state = DataReader().spell_state_by_id.get(state_id)
    if state is None:
        return False

    if is_state_removal_effect(effect):
        return state_id in active_state_ids and bool(
            state.preventsFight or state.preventsSpellCast or state.cantDealDamage or state.incurable
        )
    return state_id not in active_state_ids and bool(
        state.invulnerable
        or state.invulnerableMelee
        or state.invulnerableRange
        or state.cantBePushed
        or state.cantBeTackled
        or state.cantSwitchPosition
    )


def is_ap_mp_loss_effect(effect: Effect) -> bool:
    if effect.effectId == MOVEMENT_POINT_STEAL_ACTION_ID:
        return True

    data_effect = DataReader().effect_by_id[effect.effectId]
    return data_effect.characteristic in {
        CharacteristicEnum.ACTION_POINTS,
        CharacteristicEnum.MOVEMENT_POINTS,
    } and data_effect.characteristicOperator == "-"


def is_erosion_effect(effect: Effect) -> bool:
    return effect.effectId == EROSION_ACTION_ID or DataReader().effect_by_id[
        effect.effectId
    ].characteristic == CharacteristicEnum.PERMANENT_DAMAGE_PERCENT


PUSH_DESCRIPTION_IDS: frozenset[int] = frozenset(
    {
        DescriptionEnum.PUSH,
        DescriptionEnum.PUSH_ALT,
        DescriptionEnum.PUSH_FORCED,
        DescriptionEnum.PUSH_FORCED_ALT,
    }
)


def is_push_effect(effect: Effect) -> bool:
    return effect.effectId in PUSH_ACTION_IDS or _has_description(effect, PUSH_DESCRIPTION_IDS)


SELF_BUFF_DESCRIPTION_IDS: frozenset[int] = frozenset(
    {
        DescriptionEnum.BUFF_POWER,
        DescriptionEnum.BUFF_SPELL_POWER,
        DescriptionEnum.BUFF_DAMAGE,
        DescriptionEnum.BUFF_ACTION_POINTS,
    }
)


SELF_BENEFICIAL_CHARACTERISTIC_IDS: frozenset[int] = frozenset(
    {
        CharacteristicEnum.ACTION_POINTS,
        CharacteristicEnum.STRENGTH,
        CharacteristicEnum.VITALITY,
        CharacteristicEnum.WISDOM,
        CharacteristicEnum.CHANCE,
        CharacteristicEnum.AGILITY,
        CharacteristicEnum.INTELLIGENCE,
        CharacteristicEnum.ALL_DAMAGES_BONUS,
        CharacteristicEnum.CRITICAL_HIT,
        CharacteristicEnum.RANGE,
        CharacteristicEnum.MOVEMENT_POINTS,
        CharacteristicEnum.WEAPON_DAMAGES_PERCENT,
        CharacteristicEnum.PHYSICAL_DAMAGES_BONUS,
        CharacteristicEnum.EARTH_ELEMENT_RESIST_PERCENT,
        CharacteristicEnum.FIRE_ELEMENT_RESIST_PERCENT,
        CharacteristicEnum.WATER_ELEMENT_RESIST_PERCENT,
        CharacteristicEnum.AIR_ELEMENT_RESIST_PERCENT,
        CharacteristicEnum.NEUTRAL_ELEMENT_RESIST_PERCENT,
        CharacteristicEnum.POWER,
        CharacteristicEnum.MAX_SUMMONED_CREATURES_BOOST,
        CharacteristicEnum.HEAL_BONUS,
        CharacteristicEnum.REFLECT_DAMAGE,
        CharacteristicEnum.EARTH_ELEMENT_REDUCTION,
        CharacteristicEnum.FIRE_ELEMENT_REDUCTION,
        CharacteristicEnum.WATER_ELEMENT_REDUCTION,
        CharacteristicEnum.AIR_ELEMENT_REDUCTION,
        CharacteristicEnum.NEUTRAL_ELEMENT_REDUCTION,
        CharacteristicEnum.TRAP_DAMAGE_BONUS_PERCENT,
        CharacteristicEnum.TRAP_DAMAGE_BONUS,
        CharacteristicEnum.TACKLE_EVADE,
        CharacteristicEnum.TACKLE_BLOCK,
        CharacteristicEnum.AP_ATTACK,
        CharacteristicEnum.MP_ATTACK,
        CharacteristicEnum.PUSH_DAMAGE_BONUS,
        CharacteristicEnum.CRITICAL_DAMAGE_BONUS,
        CharacteristicEnum.EARTH_DAMAGE_BONUS,
        CharacteristicEnum.FIRE_DAMAGE_BONUS,
        CharacteristicEnum.WATER_DAMAGE_BONUS,
        CharacteristicEnum.AIR_DAMAGE_BONUS,
        CharacteristicEnum.NEUTRAL_DAMAGE_BONUS,
        CharacteristicEnum.MAX_BOMB_SUMMON,
        CharacteristicEnum.BOMB_COMBO_BONUS,
        CharacteristicEnum.MAX_LIFE,
        CharacteristicEnum.SHIELD,
        CharacteristicEnum.DAMAGES_PERCENT_SPELL,
        CharacteristicEnum.RESIST_PERCENT,
        CharacteristicEnum.WEAPON_POWER,
        CharacteristicEnum.GLYPH_POWER,
        CharacteristicEnum.DEALT_DAMAGE_MULTIPLIER,
        CharacteristicEnum.DEALT_DAMAGE_MULTIPLIER_MELEE,
        CharacteristicEnum.DEALT_DAMAGE_MULTIPLIER_DISTANCE,
        CharacteristicEnum.DEALT_DAMAGE_MULTIPLIER_WEAPON,
        CharacteristicEnum.DEALT_DAMAGE_MULTIPLIER_SPELLS,
    }
)


def is_self_beneficial_stat_effect(effect: Effect) -> bool:
    if _has_description(effect, SELF_BUFF_DESCRIPTION_IDS):
        return True

    data_effect = DataReader().effect_by_id[effect.effectId]
    return (
        data_effect.characteristicOperator == "+"
        and data_effect.characteristic in SELF_BENEFICIAL_CHARACTERISTIC_IDS
    )


SHIELD_DESCRIPTION_IDS: frozenset[int] = frozenset(
    {
        DescriptionEnum.SHIELD_FLAT,
        DescriptionEnum.SHIELD_PERCENT_LEVEL,
        DescriptionEnum.SHIELD_PERCENT_MAX_LIFE,
    }
)


def is_self_shield_effect(effect: Effect) -> bool:
    return _has_description(effect, SHIELD_DESCRIPTION_IDS)


VITALITY_BUFF_DESCRIPTION_IDS: frozenset[int] = frozenset({DescriptionEnum.BUFF_VITALITY})


def is_vitality_buff_effect(effect: Effect) -> bool:
    return _has_description(effect, VITALITY_BUFF_DESCRIPTION_IDS)


def resolve_effect_element(
    effect_element: int, primary_elem: EffectElement, effect_id: int | None = None
) -> int | None:
    if effect_element == BEST_ELEMENT or effect_id == 2822:
        return primary_elem
    if effect_element in EffectElement:
        return effect_element
    return None


def resolve_effect_damage_element(effect: Effect, primary_elem: EffectElement) -> int | None:
    return resolve_effect_element(effect.effectElement, primary_elem, effect.effectId)


@cache
def get_rune_element_for_spell(spell_id: int, primary_elem: EffectElement) -> EffectElement | None:
    """Infer a placed rune's element from the damage attached to its rune-placement effect."""
    elements: set[EffectElement] = set()
    data_reader = DataReader()
    for spell_lvl in data_reader.spell_lvl_by_spell_id.get(spell_id, []):
        for rune_effect in spell_lvl.effects:
            if rune_effect.effectId != RUNE_PLACEMENT_ACTION_ID:
                continue
            for effect in spell_lvl.effects:
                if effect.zoneDescr != rune_effect.zoneDescr or not can_target_enemy(effect):
                    continue
                if is_heal_effect(effect):
                    continue
                if (
                    data_reader.effect_by_id[effect.effectId].characteristicOperator != ""
                    and not is_fixed_neutral_damage_effect(effect)
                ):
                    continue
                element = resolve_effect_damage_element(effect, primary_elem)
                if element is None:
                    continue
                element_enum = EffectElement(element)
                if element_enum != EffectElement.NEUTRAL_ELEMENT:
                    elements.add(element_enum)

    if len(elements) != 1:
        return None
    return next(iter(elements))


def get_effect_elem_by_stat(stat_id: int) -> EffectElement:
    match stat_id:
        case CharacteristicEnum.CHANCE:
            return EffectElement.CHANCE
        case CharacteristicEnum.STRENGTH:
            return EffectElement.STRENGTH
        case CharacteristicEnum.INTELLIGENCE:
            return EffectElement.INTELLIGENCE
        case CharacteristicEnum.AGILITY:
            return EffectElement.AGILITY
        case _:
            raise ValueError(f"Unknown primary stat : {stat_id} for elem")


def get_type_effect(spell_id: int, effect: Effect) -> TypeEffect | None:
    data_effect = DataReader().effect_by_id[effect.effectId]
    description_spell = I18N().name_by_id[DataReader().spell_by_id[spell_id].descriptionId]
    if (
        data_effect.descriptionId == DescriptionEnum.MALUS_LIFE_PERCENT
        and "vie du lanceur" in description_spell.lower()
        and data_effect.isInPercent
    ):
        return TypeEffect.MALUS_LIFE_PERCENT
    if data_effect.descriptionId == DescriptionEnum.SHIELD_PERCENT_LEVEL:
        return TypeEffect.SHIELD_PERCENT_LEVEL


def get_life_point_percent_malus(life_point: int, effect: Effect) -> int:
    return int(life_point * effect.diceNum / 100)


def get_effect_shield_level_bonus(level: int, effect: Effect) -> int:
    return int(level * effect.diceNum / 100)


def get_critical_effect(spell_lvl: SpellLevelsRootItem, effect: Effect) -> Effect:
    for crit_effect in spell_lvl.criticalEffect:
        if crit_effect.effectElement == effect.effectElement:
            return crit_effect
    return effect


def base_roll(effect: Effect) -> float:
    if effect.diceNum == 0 and effect.diceSide == 0:
        return float(effect.value)
    if effect.diceSide > effect.diceNum:
        return (effect.diceNum + effect.diceSide) / 2
    return float(effect.diceNum)


_SELF_MASK_CHARS = ("C", "c", "a")


_ENEMY_MASK_CHARS = frozenset({"A", "D", "H", "I", "J", "L", "M", "S"})
_STATE_TARGET_MASK_PATTERN = re.compile(r"(?P<excluded>\*)?[Ee](?P<state_id>\d+)")


def can_self_cast(effect: Effect) -> bool:
    return any(char in effect.targetMask for char in _SELF_MASK_CHARS)


def can_target_enemy(effect: Effect) -> bool:
    return any(char in _ENEMY_MASK_CHARS for char in effect.targetMask)


def target_state_criteria_match(effect: Effect, state_ids: frozenset[int] | None) -> bool:
    for token in effect.targetMask.split(","):
        match = _STATE_TARGET_MASK_PATTERN.fullmatch(token.strip())
        if match is None:
            continue
        if state_ids is None:
            return False

        state_is_present = int(match.group("state_id")) in state_ids
        if state_is_present == (match.group("excluded") is not None):
            return False

    return True
