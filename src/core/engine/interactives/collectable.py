from collections import defaultdict
from dataclasses import dataclass
from functools import cache, cached_property

from DBDofusUnity.datas.protos.non_obf.game.common_pb2 import (
    InteractiveElement,
    StatedElement,
)
from DBDofusUnity.dofus_unity_reader.data_center.data_reader import DataReader
from DBDofusUnity.dofus_unity_reader.data_center.map_reader import MapReader
from DBDofusUnity.dofus_unity_reader.game_constants.job import HARVESTER_JOB_IDS, JobEnum
from DBDofusUnity.dofus_unity_reader.grid.map_point import MapPoint


@dataclass
class Collectable:
    map_id: int
    interactive_element: InteractiveElement
    skill: InteractiveElement.InteractiveElementSkill
    resource_item_id: int

    @cached_property
    def job_id(self) -> JobEnum:
        return JobEnum(DataReader().skill_by_id[self.skill.skill_id].parentJobId)

    def is_farmable(self, job_lvl: int) -> bool:
        related_skill_data = DataReader().skill_by_id[self.skill.skill_id]
        if related_skill_data.levelMin > job_lvl:
            return False
        related_job = related_skill_data.parentJobId
        return related_job in HARVESTER_JOB_IDS

    @property
    def skill_ids(self) -> list[int]:
        return [skill.skill_id for skill in self.interactive_element.enabled_skills]

    @cached_property
    def mp(self) -> MapPoint:
        cell_id = (
            MapReader()
            .get_ref_data_by_element_id_by_map_id(self.map_id)[self.interactive_element.element_id]
            .cellId
        )
        if cell_id is None:
            raise ValueError("Player can't stand on a cell that have no id !")
        return MapPoint.from_cell_id(cell_id)


@cache
def get_resource_item_ids_by_job_id() -> dict[int, frozenset[int]]:
    resource_item_ids_by_job_id: defaultdict[int, set[int]] = defaultdict(set)
    for skill in DataReader().skill_by_id.values():
        if skill.parentJobId not in HARVESTER_JOB_IDS or skill.gatheredRessourceItem <= 0:
            continue
        resource_item_ids_by_job_id[skill.parentJobId].add(skill.gatheredRessourceItem)

    return {
        job_id: frozenset(resource_item_ids)
        for job_id, resource_item_ids in resource_item_ids_by_job_id.items()
    }


@cache
def get_job_ids_by_resource_item_id() -> dict[int, frozenset[JobEnum]]:
    job_ids_by_resource_item_id: defaultdict[int, set[JobEnum]] = defaultdict(set)
    for job_id, item_ids in get_resource_item_ids_by_job_id().items():
        for item_id in item_ids:
            job_ids_by_resource_item_id[item_id].add(JobEnum(job_id))

    return {
        item_id: frozenset(job_ids)
        for item_id, job_ids in job_ids_by_resource_item_id.items()
    }


def get_stated_element_collectable(
    stated_element: StatedElement,
    interactive_element_by_id: dict[int, InteractiveElement],
    map_id: int,
    jobs_lvl_by_id: dict[int, int],
) -> Collectable | None:
    if stated_element.state != 0:
        return None

    related_interactive = interactive_element_by_id.get(stated_element.element_id)
    if (
        not related_interactive
        or related_interactive.on_current_map is not True
        or len(related_interactive.enabled_skills) == 0
    ):
        return None

    skill = related_interactive.enabled_skills[0]
    data_skill = DataReader().skill_by_id[skill.skill_id]
    if data_skill.gatheredRessourceItem in [-1, 0]:
        return None

    collectable = Collectable(
        map_id=map_id,
        interactive_element=related_interactive,
        skill=skill,
        resource_item_id=data_skill.gatheredRessourceItem,
    )

    player_job_level = jobs_lvl_by_id.get(data_skill.parentJobId, 1)
    if not collectable.is_farmable(player_job_level):
        return None

    return collectable
