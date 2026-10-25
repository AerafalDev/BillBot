from DBDofusUnity.dofus_unity_reader.data_center.map_reader import MapReader
from DBDofusUnity.dofus_unity_reader.grid.map_point import MapPoint
from DBDofusUnity.dofus_unity_reader.models.datas.spell_levels_root import SpellLevelsRootItem

from src.core.engine.contexts import AttackContext
from src.core.engine.fights.attack.rejection_stat import RejectionStat
from src.core.engine.fights.los_detector import LosDetector
from src.core.engine.fights.spell_modifier import SpellModifiers


def can_cast_spell_on_mp(
    context: AttackContext,
    from_mp: MapPoint,
    spell_lvl: SpellLevelsRootItem,
    mp: MapPoint,
    modifiers: SpellModifiers,
    entities_mp: set[MapPoint],
    entities_id_by_mp: dict[MapPoint, int],
    rejection_stats: dict[RejectionStat, int],
) -> bool:
    targetable_mp_data = MapReader().get_cell_data_by_cell_id(context.map_id, mp.cell_id)
    if not targetable_mp_data.mov:
        rejection_stats[RejectionStat.CELL_NOT_WALKABLE] += 1
        return False

    entity_id = entities_id_by_mp.get(mp)
    if modifiers.needs_free_cell and entity_id is not None:
        rejection_stats[RejectionStat.CELL_NOT_FREE] += 1
        return False
    if modifiers.needs_visible_entity and (
        entity_id is None or mp.cell_id in context.invisible_enemy_cell_ids
    ):
        rejection_stats[RejectionStat.TARGET_NOT_VISIBLE] += 1
        return False

    if entity_id is not None and modifiers.max_cast_per_target > 0:
        count_casted_on_target = context.count_casted_by_spell_id_and_target_id.get(
            (spell_lvl.spellId, entity_id), 0
        )
        if count_casted_on_target >= modifiers.max_cast_per_target:
            rejection_stats[RejectionStat.MAX_CAST_PER_TARGET] += 1
            return False

    if modifiers.cast_test_los and not LosDetector.los_between(
        map_id=context.map_id,
        taken_mps=entities_mp,
        start=from_mp,
        end=mp,
    ):
        rejection_stats[RejectionStat.NO_LOS] += 1
        return False

    return True
