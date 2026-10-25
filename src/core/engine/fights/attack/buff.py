from DBDofusUnity.dofus_unity_reader.models.datas.spell_levels_root import (
    Effect,
    SpellLevelsRootItem,
)
from src.core.engine.contexts import AttackContext
from src.core.engine.fights.attack.spell_filter import collect_castable_spells
from src.core.engine.fights.effect import (
    is_beneficial_self_state_effect,
    can_self_cast,
    is_self_beneficial_stat_effect,
    is_self_shield_effect,
)
from src.core.engine.fights.spell_modifier import SpellModifiers


def _self_beneficial_effect(effect: Effect, context: AttackContext) -> bool:
    return can_self_cast(effect) and (
        is_self_beneficial_stat_effect(effect)
        or is_self_shield_effect(effect)
        or is_beneficial_self_state_effect(effect, context.own_state_ids)
    )


def get_valid_self_buff_spells_for_turn(
    context: AttackContext,
) -> list[tuple[SpellLevelsRootItem, Effect, SpellModifiers]]:
    valid_spells = collect_castable_spells(
        context, lambda effect: _self_beneficial_effect(effect, context)
    )
    return [
        (spell_lvl, effect, modifiers)
        for spell_lvl, effect, modifiers in valid_spells
        if spell_lvl.maxStack > 0
        or context.own_active_stack_count_by_spell_id.get(spell_lvl.spellId, 0) == 0
    ]
