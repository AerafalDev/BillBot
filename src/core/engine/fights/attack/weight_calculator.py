import re
from collections.abc import Mapping
from functools import cache

from DBDofusUnity.datas.protos.non_obf.game.common_pb2 import CharacterCharacteristic
from DBDofusUnity.dofus_unity_reader.data_center.data_reader import DataReader
from DBDofusUnity.dofus_unity_reader.data_center.i18n import I18N
from DBDofusUnity.dofus_unity_reader.game_constants.characteristic import (
    CharacteristicEnum,
    EffectElement,
    TypeEffect,
)
from DBDofusUnity.dofus_unity_reader.grid.map_point import MapPoint
from DBDofusUnity.dofus_unity_reader.models.datas.monsters_root import MonsterGrade
from DBDofusUnity.dofus_unity_reader.models.datas.spell_levels_root import Effect, SpellLevelsRootItem
from DBDofusUnity.dofus_unity_reader.models.datas.spellstatesroot import SpellstatesrootItem
from src.core.engine.contexts import AttackContext
from src.core.engine.fights.attack.enemy_data import FULLY_INVULNERABLE_STATE_IDS, EnemyData
from src.core.engine.fights.attack.push import estimate_collision_damage, estimate_push_endpoint
from src.core.engine.fights.damage_calculator import DamageCalculator
from src.core.engine.fights.effect import (
    ADD_STATE_ACTION_ID,
    REMOVE_STATE_ACTION_ID,
    RUNE_TRIGGER_ACTION_ID,
    base_roll,
    can_target_enemy,
    get_state_id,
    get_effect_shield_level_bonus,
    get_life_point_percent_malus,
    get_type_effect,
    is_fixed_neutral_damage_effect,
    is_instant_kill_effect,
    is_heal_effect,
    is_life_steal_effect,
    is_push_effect,
    is_state_effect,
    is_state_removal_effect,
    is_ap_mp_loss_effect,
    is_erosion_effect,
    resolve_effect_damage_element,
    target_state_criteria_match,
)
from src.core.engine.fights.spell_modifier import SpellModifiers
from src.core.engine.fights.stats.characteristic import get_stat_by_id

LIFE_STEAL_PATTERN = re.compile(r"\bvol\b", re.IGNORECASE)


class AttackWeights:
    LIFE_RECOVERY_MULTIPLIER = 2
    LIFE_STEAL_RATIO = 0.5
    ENEMY_KILL_BONUS = 1.0
    SUMMONED_KILL_BONUS = 0.5
    SUMMONED_DAMAGE_DIVISOR = 2

    ALLY_HIT_PENALTY_FACTOR = 0.1
    INVISIBLE_ENEMY_WEIGHT_FACTOR = 0.3
    PRIMARY_ELEMENT_SCORE_BONUS = 0.2
    ACTION_POINT_LOSS_VALUE = 3.0
    MOVEMENT_POINT_LOSS_VALUE = 1.5
    PUSH_DISTANCE_VALUE = 1.5
    PUSH_OUT_OF_RANGE_VALUE = 6.0
    PUSH_TOWARD_ALLY_PENALTY = 1.5
    STATE_PREVENTS_FIGHT_VALUE = 10.0
    STATE_PREVENTS_CAST_VALUE = 8.0
    STATE_PREVENTS_DAMAGE_VALUE = 7.0
    STATE_PREVENTS_HEALING_VALUE = 2.0
    EROSION_DAMAGE_WINDOW_PER_TURN = 0.3


def calculate_attack_weight(
    damage_calculator: DamageCalculator,
    context: AttackContext,
    impact_mps: set[MapPoint],
    spell_lvl: SpellLevelsRootItem,
    effect: Effect,
    target_mp: MapPoint,
    enemies_data: list[EnemyData],
    modifiers: SpellModifiers,
    caster_mp: MapPoint | None = None,
) -> float:
    caster_mp = caster_mp or context.player_map_point
    data_effect = DataReader().effect_by_id[effect.effectId]
    description_effect = I18N().name_by_id[data_effect.descriptionId]

    dmg_weight, effective_damage = calculate_damage_weight(
        damage_calculator, context, spell_lvl, effect, target_mp, impact_mps, enemies_data, caster_mp
    )

    life_malus, shield_bonus = calculate_life_modifiers(context, spell_lvl)
    has_life_steal = is_life_steal(description_effect) or any(
        is_life_steal_effect(zone_effect) for zone_effect in _co_zone_effects(spell_lvl, effect)
    )
    life_stolen = effective_damage * AttackWeights.LIFE_STEAL_RATIO if has_life_steal else 0.0

    life_recovery_weight = calculate_life_recovery_weight(context, life_stolen, life_malus, shield_bonus)

    ally_penalty = _ally_hit_penalty(context, impact_mps)

    return (dmg_weight * life_recovery_weight * ally_penalty) / max(modifiers.ap_cost, 1)


def _ally_hit_penalty(context: AttackContext, impact_mps: set[MapPoint]) -> float:
    enemy_ids = {actor.actor_id for actor in context.enemy_actors}
    ally_cell_ids = {
        actor.disposition.cell_id
        for actor in context.actor_by_id.values()
        if actor.actor_id != context.player_character_id
        and actor.actor_id not in enemy_ids
        and actor.disposition.cell_id != -1
    }
    allies_hit = sum(1 for mp in impact_mps if mp.cell_id in ally_cell_ids)
    return AttackWeights.ALLY_HIT_PENALTY_FACTOR**allies_hit


@cache
def is_life_steal(description_effect: str) -> bool:
    return bool(LIFE_STEAL_PATTERN.search(description_effect))


def calculate_life_modifiers(context: AttackContext, spell_lvl: SpellLevelsRootItem) -> tuple[int, int]:
    life_point_malus = 0
    shield_bonus = 0

    for effect in spell_lvl.effects:
        type_effect = get_type_effect(spell_lvl.spellId, effect)
        if type_effect is None:
            continue

        if type_effect == TypeEffect.MALUS_LIFE_PERCENT:
            life_point_malus += get_life_point_percent_malus(context.life_point, effect)
        elif type_effect == TypeEffect.SHIELD_PERCENT_LEVEL:
            shield_bonus += get_effect_shield_level_bonus(context.player_level, effect)

    return life_point_malus, shield_bonus


def calculate_life_recovery_weight(
    context: AttackContext,
    life_stolen: float,
    life_malus: int,
    shield_bonus: int,
) -> float:
    new_life = context.life_point + life_stolen - life_malus + shield_bonus
    new_life_percentage = min(new_life / context.max_life_point, 1.0)

    return 1 + ((new_life_percentage - context.life_percentage) * AttackWeights.LIFE_RECOVERY_MULTIPLIER)


def _co_zone_effects(spell_lvl: SpellLevelsRootItem, representative: Effect) -> list[Effect]:
    return [effect for effect in spell_lvl.effects if effect.zoneDescr == representative.zoneDescr]


def _targeted_co_zone_effects(
    spell_lvl: SpellLevelsRootItem,
    representative: Effect,
    target_state_ids: frozenset[int] | None,
    rune_elements: frozenset[EffectElement] | None = None,
) -> list[Effect]:
    """Resolve state masks in effect order so state changes affect later effects in the cast."""
    has_rune_trigger = any(effect.effectId == RUNE_TRIGGER_ACTION_ID for effect in spell_lvl.effects)
    active_state_ids = set(target_state_ids) if target_state_ids is not None else None
    targeted_effects: list[Effect] = []

    for effect in sorted(_co_zone_effects(spell_lvl, representative), key=lambda item: item.order):
        if not can_target_enemy(effect) or not target_state_criteria_match(
            effect, frozenset(active_state_ids) if active_state_ids is not None else None
        ):
            continue

        # The trigger action's four lifesteal rows share a mask; only the rune's element applies.
        if has_rune_trigger and is_life_steal_effect(effect):
            try:
                effect_element = EffectElement(effect.effectElement)
            except ValueError:
                continue
            if rune_elements is None or effect_element not in rune_elements:
                continue

        targeted_effects.append(effect)
        if active_state_ids is None or not is_state_effect(effect):
            continue

        state_id = get_state_id(effect)
        if state_id is None:
            continue
        if effect.effectId == REMOVE_STATE_ACTION_ID:
            active_state_ids.discard(state_id)
        elif effect.effectId == ADD_STATE_ACTION_ID:
            active_state_ids.add(state_id)

    return targeted_effects


def _spell_damage_effects(
    targeted_effects: list[Effect], primary_elem: EffectElement
) -> list[Effect]:
    """Return damage effects whose target masks match the affected enemy."""
    return [
        effect for effect in targeted_effects
        if not is_heal_effect(effect)
        and (
            resolve_effect_damage_element(effect, primary_elem) is not None
            or is_instant_kill_effect(effect)
        )
        and (
            DataReader().effect_by_id[effect.effectId].characteristicOperator == ""
            or is_fixed_neutral_damage_effect(effect)
        )
    ]


def _spell_push_effect(targeted_effects: list[Effect]) -> Effect | None:
    for effect in targeted_effects:
        if is_push_effect(effect):
            return effect
    return None


def _state_metadata(state_id: int) -> SpellstatesrootItem | None:
    return DataReader().spell_state_by_id.get(state_id)


def _state_removed_before(
    targeted_effects: list[Effect],
    state_id: int,
    before_order: int,
) -> bool:
    return any(
        effect.order < before_order
        and is_state_removal_effect(effect)
        and get_state_id(effect) == state_id
        for effect in targeted_effects
    )


def _will_remove_invulnerability_before(
    targeted_effects: list[Effect],
    enemy_data: EnemyData,
    before_order: int,
    is_melee: bool,
) -> bool:
    for state_id in enemy_data.state_ids:
        state = _state_metadata(state_id)
        state_blocks_damage = bool(
            state
            and (
                state.invulnerable
                or (state.invulnerableMelee if is_melee else state.invulnerableRange)
            )
        )
        if state_id not in FULLY_INVULNERABLE_STATE_IDS and not state_blocks_damage:
            continue
        if _state_removed_before(targeted_effects, state_id, before_order):
            return True
    return False


def _will_be_pushable_before(
    targeted_effects: list[Effect],
    enemy_data: EnemyData,
    push_order: int,
) -> bool:
    return not any(
        (state := _state_metadata(state_id)) is not None
        and (state.cantBePushed or state.cantBeMoved)
        and not _state_removed_before(targeted_effects, state_id, push_order)
        for state_id in enemy_data.state_ids
    )


def _tactical_effect_weight(
    targeted_effects: list[Effect],
    enemy_data: EnemyData,
) -> float:
    weight = 0.0
    has_push = any(is_push_effect(effect) for effect in targeted_effects)

    for effect in targeted_effects:
        if is_erosion_effect(effect):
            erosion = min(
                max(base_roll(effect), 0),
                max(50 - enemy_data.permanent_damage_percent, 0),
            )
            duration = 3 if effect.duration < 0 else min(max(effect.duration, 1), 3)
            damage_window = min(
                enemy_data.life_point,
                enemy_data.max_life_point * AttackWeights.EROSION_DAMAGE_WINDOW_PER_TURN * duration,
            )
            weight = max(weight, damage_window * erosion / 100)
            continue
        if not is_state_effect(effect):
            continue
        state_id = get_state_id(effect)
        if state_id is None:
            continue
        state = _state_metadata(state_id)
        if state is None:
            continue

        if is_state_removal_effect(effect):
            if state_id not in enemy_data.state_ids:
                continue
            if state.invulnerable or state.invulnerableMelee or state.invulnerableRange:
                weight = max(weight, AttackWeights.STATE_PREVENTS_FIGHT_VALUE / 2)
            elif (state.cantBePushed or state.cantBeMoved) and has_push:
                weight = max(weight, AttackWeights.PUSH_DISTANCE_VALUE)
            continue

        if state_id in enemy_data.state_ids:
            continue
        values = [
            AttackWeights.STATE_PREVENTS_FIGHT_VALUE if state.preventsFight else 0.0,
            AttackWeights.STATE_PREVENTS_CAST_VALUE if state.preventsSpellCast else 0.0,
            AttackWeights.STATE_PREVENTS_DAMAGE_VALUE if state.cantDealDamage else 0.0,
            AttackWeights.STATE_PREVENTS_HEALING_VALUE if state.incurable else 0.0,
        ]
        duration = 3 if effect.duration < 0 else min(max(effect.duration, 1), 3)
        weight = max(weight, max(values) * duration)

    return weight


def _point_loss_weight(effect: Effect, enemy_data: EnemyData) -> float:
    data_effect = DataReader().effect_by_id[effect.effectId]
    if effect.effectId == 77 or data_effect.characteristic == CharacteristicEnum.MOVEMENT_POINTS:
        dodge_stat = CharacteristicEnum.DODGE_PM_LOST_PROBABILITY
        available_points = enemy_data.monster_grade.movementPoints
        default_dodge = enemy_data.monster_grade.pmDodge
        point_value = AttackWeights.MOVEMENT_POINT_LOSS_VALUE
    elif data_effect.characteristic == CharacteristicEnum.ACTION_POINTS:
        dodge_stat = CharacteristicEnum.DODGE_PA_LOST_PROBABILITY
        available_points = enemy_data.monster_grade.actionPoints
        default_dodge = enemy_data.monster_grade.paDodge
        point_value = AttackWeights.ACTION_POINT_LOSS_VALUE
    else:
        return 0.0

    dodge_percent = (
        get_stat_by_id(enemy_data.characteristic_by_id[dodge_stat])
        if dodge_stat in enemy_data.characteristic_by_id
        else default_dodge
    )
    amount = min(max(base_roll(effect), 0), max(available_points, 0))
    expected_amount = amount * (100 - min(max(dodge_percent, 0), 100)) / 100
    return expected_amount * point_value


def _ally_push_penalty(context: AttackContext, enemy_data: EnemyData, end_mp: MapPoint) -> float:
    enemy_ids = {actor.actor_id for actor in context.enemy_actors}
    ally_mps = [
        MapPoint.from_cell_id(actor.disposition.cell_id)
        for actor in context.actor_by_id.values()
        if actor.actor_id != context.player_character_id
        and actor.actor_id not in enemy_ids
        and actor.disposition.cell_id != -1
    ]
    if not ally_mps:
        return 0.0

    before_distance = min(enemy_data.map_point.distance_to_map_point(ally_mp) for ally_mp in ally_mps)
    after_distance = min(end_mp.distance_to_map_point(ally_mp) for ally_mp in ally_mps)
    return max(before_distance - after_distance, 0) * AttackWeights.PUSH_TOWARD_ALLY_PENALTY


def _push_position_weight(
    context: AttackContext,
    caster_mp: MapPoint,
    enemy_data: EnemyData,
    end_mp: MapPoint,
) -> float:
    distance_before = caster_mp.distance_to_map_point(enemy_data.map_point)
    distance_after = caster_mp.distance_to_map_point(end_mp)
    weight = (distance_after - distance_before) * AttackWeights.PUSH_DISTANCE_VALUE

    if distance_before <= enemy_data.max_spell_range < distance_after:
        weight += AttackWeights.PUSH_OUT_OF_RANGE_VALUE

    return weight - _ally_push_penalty(context, enemy_data, end_mp)


def _estimate_damage_at(
    damage_calculator: DamageCalculator,
    context: AttackContext,
    caster_mp: MapPoint,
    spell_lvl: SpellLevelsRootItem,
    effect: Effect,
    damage_effects: list[Effect],
    target_mp: MapPoint,
    at_mp: MapPoint,
    monster_grade: MonsterGrade | None,
    target_life_point: int = 0,
    target_max_life_point: int = 0,
    target_characteristic_by_id: Mapping[int, CharacterCharacteristic] | None = None,
) -> float:
    distance = target_mp.distance_to_map_point(at_mp)
    applied_steps = min(distance, effect.zoneDescr.maxDamageDecreaseApplyCount)
    damage_decrease = effect.zoneDescr.damageDecreaseStepPercent * applied_steps / 100.0

    is_melee = caster_mp.distance_to_map_point(at_mp) == 1
    raw_damage = sum(
        damage_calculator.get_damage_effect(
            damage_effect,
            spell_lvl,
            monster_grade,
            context.characteristic_by_id,
            is_melee,
            context.primary_elem,
            context.modifier_by_type_and_spell_id,
            caster_life_point=context.life_point,
            caster_max_life_point=context.max_life_point,
            target_life_point=target_life_point,
            target_max_life_point=target_max_life_point,
            target_characteristic_by_id=target_characteristic_by_id,
        )
        for damage_effect in damage_effects
    )
    return max(raw_damage * (1 - damage_decrease), 0)


def calculate_damage_weight(
    damage_calculator: DamageCalculator,
    context: AttackContext,
    spell_lvl: SpellLevelsRootItem,
    effect: Effect,
    target_mp: MapPoint,
    impact_mps: set[MapPoint],
    enemies_data: list[EnemyData],
    caster_mp: MapPoint,
) -> tuple[float, float]:
    enemy_killed = 0.0
    enemy_dmg_weight = 0.0
    total_effective_damage = 0.0
    has_primary_element_damage = False

    occupied_cell_ids: set[int] = set()
    push_damage_bonus = 0

    for enemy_data in enemies_data:
        if enemy_data.map_point not in impact_mps:
            continue

        if enemy_data.life_point <= 0 or enemy_data.is_hidden:
            continue

        targeted_effects = _targeted_co_zone_effects(
            spell_lvl,
            effect,
            enemy_data.state_ids,
            context.own_rune_elements_by_cell.get(enemy_data.map_point.cell_id, frozenset()),
        )
        damage_effects = _spell_damage_effects(targeted_effects, context.primary_elem)
        push_effect = _spell_push_effect(targeted_effects)
        push_distance = push_effect.diceNum if push_effect is not None else None
        if push_distance is not None and not occupied_cell_ids:
            occupied_cell_ids = {
                actor.disposition.cell_id
                for actor in context.actor_by_id.values()
                if actor.disposition.cell_id != -1
            }
            push_damage_bonus = get_stat_by_id(
                context.characteristic_by_id.get(CharacteristicEnum.PUSH_DAMAGE_BONUS)
            )

        first_damage_order = min((damage_effect.order for damage_effect in damage_effects), default=effect.order)
        is_melee = caster_mp.distance_to_map_point(enemy_data.map_point) == 1
        can_damage_target = not enemy_data.is_invulnerable_for(is_melee) or (
            _will_remove_invulnerability_before(
                targeted_effects, enemy_data, first_damage_order, is_melee
            )
        )
        if can_damage_target and any(
            resolve_effect_damage_element(damage_effect, context.primary_elem) == context.primary_elem
            for damage_effect in damage_effects
        ):
            has_primary_element_damage = True
        damage = (
            _estimate_damage_at(
                damage_calculator,
                context,
                caster_mp,
                spell_lvl,
                effect,
                damage_effects,
                target_mp,
                enemy_data.map_point,
                enemy_data.monster_grade,
                enemy_data.life_point,
                enemy_data.max_life_point,
                enemy_data.characteristic_by_id,
            )
            if can_damage_target
            else 0.0
        )

        if can_damage_target and any(
            is_instant_kill_effect(zone_effect) for zone_effect in targeted_effects
        ):
            damage = enemy_data.life_point

        if push_effect is not None and _will_be_pushable_before(targeted_effects, enemy_data, push_effect.order):
            push_end_mp, moved = estimate_push_endpoint(
                caster_mp,
                enemy_data.map_point,
                push_effect.diceNum,
                context.map_id,
                occupied_cell_ids - {enemy_data.map_point.cell_id},
            )
            if moved > 0:
                if push_effect.effectId != 1103 and can_damage_target:
                    damage += estimate_collision_damage(
                        caster_mp,
                        enemy_data.map_point,
                        push_effect.diceNum,
                        context.map_id,
                        occupied_cell_ids - {enemy_data.map_point.cell_id},
                        context.player_level,
                        push_damage_bonus,
                    )
                enemy_dmg_weight += _push_position_weight(context, caster_mp, enemy_data, push_end_mp)

        for zone_effect in targeted_effects:
            if is_ap_mp_loss_effect(zone_effect):
                enemy_dmg_weight += _point_loss_weight(zone_effect, enemy_data)

        effective_damage = min(damage, enemy_data.life_point)
        total_effective_damage += effective_damage

        if damage >= enemy_data.life_point:
            enemy_killed += (
                AttackWeights.SUMMONED_KILL_BONUS
                if enemy_data.is_summoned
                else AttackWeights.ENEMY_KILL_BONUS
            )

        enemy_health_percentage = enemy_data.life_point / enemy_data.max_life_point
        damage_efficiency = effective_damage / enemy_health_percentage
        if enemy_data.is_summoned:
            damage_efficiency /= AttackWeights.SUMMONED_DAMAGE_DIVISOR

        enemy_dmg_weight += damage_efficiency

        if effective_damage < enemy_data.life_point:
            enemy_dmg_weight += _tactical_effect_weight(targeted_effects, enemy_data)

    known_enemy_mps = {enemy_data.map_point for enemy_data in enemies_data}
    for invisible_mp in impact_mps:
        if invisible_mp.cell_id not in context.invisible_enemy_cell_ids or invisible_mp in known_enemy_mps:
            continue

        unknown_state_effects = _targeted_co_zone_effects(
            spell_lvl,
            effect,
            None,
            context.own_rune_elements_by_cell.get(invisible_mp.cell_id, frozenset()),
        )
        unknown_state_damage_effects = _spell_damage_effects(
            unknown_state_effects, context.primary_elem
        )
        if any(
            resolve_effect_damage_element(damage_effect, context.primary_elem) == context.primary_elem
            for damage_effect in unknown_state_damage_effects
        ):
            has_primary_element_damage = True
        damage = _estimate_damage_at(
            damage_calculator,
            context,
            caster_mp,
            spell_lvl,
            effect,
            unknown_state_damage_effects,
            target_mp,
            invisible_mp,
            None,
        )
        enemy_dmg_weight += damage * AttackWeights.INVISIBLE_ENEMY_WEIGHT_FACTOR

    damage_weight = enemy_dmg_weight * (1 + enemy_killed)
    if has_primary_element_damage:
        damage_weight *= 1 + AttackWeights.PRIMARY_ELEMENT_SCORE_BONUS
    return damage_weight, total_effective_damage
