from dataclasses import dataclass
from enum import StrEnum


class HarvestResourceFilterMode(StrEnum):
    ALL = "all"
    INCLUDE = "include"
    EXCLUDE = "exclude"


@dataclass(frozen=True)
class HarvestResourceFilter:
    mode: HarvestResourceFilterMode = HarvestResourceFilterMode.ALL
    item_ids: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        if self.mode is HarvestResourceFilterMode.INCLUDE and not self.item_ids:
            raise ValueError("An include filter must contain at least one resource")

    @property
    def is_active(self) -> bool:
        return self.mode is not HarvestResourceFilterMode.ALL and bool(self.item_ids)

    def allows(self, item_id: int) -> bool:
        if self.mode is HarvestResourceFilterMode.INCLUDE:
            return item_id in self.item_ids
        if self.mode is HarvestResourceFilterMode.EXCLUDE:
            return item_id not in self.item_ids
        return True
