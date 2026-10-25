from DBDofusUnity.dofus_unity_reader.data_center.data_reader import DataReader
from DBDofusUnity.dofus_unity_reader.game_constants.job import JobEnum

from src.controller.game_data import GameDataController
from src.core.engine.interactives.collectable import get_resource_item_ids_by_job_id


def get_map_ids_to_explore(map_ids: set[int], target_job_id: JobEnum | None = None) -> set[int]:
    map_ids_checked = GameDataController().get_map_ids_checked()
    item_job_by_gfx = GameDataController().get_item_job_by_gfx()

    map_ids_to_check: set[int] = set()

    item_knows = set((item_id for item_id, _ in item_job_by_gfx.values()))
    target_resource_item_ids = (
        get_resource_item_ids_by_job_id().get(target_job_id, frozenset())
        if target_job_id is not None
        else None
    )

    for map_id in map_ids:
        if map_id in map_ids_checked:
            continue
        sub_area = DataReader().map_info_by_map_id[map_id].subAreaId
        harvestable_items_sub_area = DataReader().sub_area_by_id[sub_area].harvestables
        for item in harvestable_items_sub_area:
            if target_resource_item_ids is not None and item not in target_resource_item_ids:
                continue
            if item not in item_knows and item in DataReader().gathered_item_ids:
                map_ids_to_check.add(map_id)
                break

    return map_ids_to_check
