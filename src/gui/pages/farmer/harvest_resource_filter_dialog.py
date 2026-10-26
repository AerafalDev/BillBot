from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import ComboBox, PushButton

from DBDofusUnity.dofus_unity_reader.data_center.data_reader import DataReader
from DBDofusUnity.dofus_unity_reader.data_center.i18n import I18N
from DBDofusUnity.dofus_unity_reader.game_constants.job import HARVESTER_JOB_IDS, JobEnum
from src.core.engine.interactives.collectable import get_resource_item_ids_by_job_id
from src.core.engine.interactives.harvest_resource_filter import (
    HarvestResourceFilter,
    HarvestResourceFilterMode,
)


FILTER_MODE_LABELS = {
    HarvestResourceFilterMode.ALL: "All resources",
    HarvestResourceFilterMode.INCLUDE: "Include selected resources",
    HarvestResourceFilterMode.EXCLUDE: "Exclude selected resources",
}


class HarvestResourceFilterDialog(QDialog):
    def __init__(
        self,
        resource_filter: HarvestResourceFilter,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Harvest resource filter")
        self.resize(480, 560)

        self._resource_ids_by_job_id = get_resource_item_ids_by_job_id()
        self._all_resource_item_ids: set[int] = set()
        for job_id, item_ids in self._resource_ids_by_job_id.items():
            if job_id == JobEnum.BASE:
                continue
            self._all_resource_item_ids.update(item_ids)
        self._item_by_id = DataReader().item_by_id
        self._resource_name_by_id: dict[int, str] = {
            item_id: I18N().name_by_id.get(item.nameId, f"Unknown {item_id}")
            for item_id in self._all_resource_item_ids
            if (item := self._item_by_id.get(item_id)) is not None
        }
        self._selected_item_ids = set(resource_filter.item_ids) & self._all_resource_item_ids

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Choose a profession to display only its resources. Selections from other professions stay selected.",
                self,
            )
        )

        self.filter_mode_combo = ComboBox(self)
        for mode, label in FILTER_MODE_LABELS.items():
            self.filter_mode_combo.addItem(label, userData=mode)
        self.filter_mode_combo.setCurrentIndex(self.filter_mode_combo.findData(resource_filter.mode))
        layout.addWidget(self.filter_mode_combo)

        self.job_combo = ComboBox(self)
        self.job_combo.addItem("All professions", userData=None)
        for job_id in sorted(HARVESTER_JOB_IDS - {JobEnum.BASE}):
            job = DataReader().job_by_id.get(job_id)
            if job is None:
                continue
            self.job_combo.addItem(I18N().name_by_id.get(job.nameId, "Unknown"), userData=job_id)
        layout.addWidget(self.job_combo)

        self.resource_list = QListWidget(self)
        layout.addWidget(self.resource_list, stretch=1)

        selection_buttons = QHBoxLayout()
        self.select_all_button = PushButton("Select all in profession", self)
        self.clear_visible_button = PushButton("Clear visible resources", self)
        selection_buttons.addWidget(self.select_all_button)
        selection_buttons.addWidget(self.clear_visible_button)
        layout.addLayout(selection_buttons)

        self.status = QLabel("", self)
        layout.addWidget(self.status)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        layout.addWidget(self.button_box)

        self.filter_mode_combo.currentIndexChanged.connect(self.refresh_resource_list)
        self.job_combo.currentIndexChanged.connect(self.refresh_resource_list)
        self.resource_list.itemChanged.connect(self.on_resource_checked_changed)
        self.select_all_button.clicked.connect(self.select_visible_resources)
        self.clear_visible_button.clicked.connect(self.clear_visible_resources)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self.refresh_resource_list()

    def get_resource_filter(self) -> HarvestResourceFilter:
        mode = self.filter_mode_combo.currentData()
        return HarvestResourceFilter(mode=mode, item_ids=frozenset(self._selected_item_ids))

    def refresh_resource_list(self) -> None:
        target_job_id = self.job_combo.currentData()
        item_ids = (
            self._resource_ids_by_job_id.get(target_job_id, frozenset())
            if target_job_id is not None
            else frozenset(
                item_id
                for job_id, job_item_ids in self._resource_ids_by_job_id.items()
                if job_id != JobEnum.BASE
                for item_id in job_item_ids
            )
        )

        self.resource_list.blockSignals(True)
        self.resource_list.clear()
        def get_resource_sort_key(item_id: int) -> tuple[int, str]:
            item = self._item_by_id.get(item_id)
            return (
                (item.level or 0) if item is not None else 0,
                self._resource_name_by_id.get(item_id, f"Unknown {item_id}").casefold(),
            )

        for item_id in sorted(item_ids, key=get_resource_sort_key):
            item = self._item_by_id.get(item_id)
            level = (item.level or 0) if item is not None else 0
            row = QListWidgetItem(f"{self._resource_name_by_id.get(item_id, f'Unknown {item_id}')} (level {level})")
            row.setData(Qt.ItemDataRole.UserRole, item_id)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(
                Qt.CheckState.Checked if item_id in self._selected_item_ids else Qt.CheckState.Unchecked
            )
            self.resource_list.addItem(row)
        self.resource_list.blockSignals(False)
        self.update_status()

    def on_resource_checked_changed(self, item: QListWidgetItem) -> None:
        item_id = item.data(Qt.ItemDataRole.UserRole)
        if item_id is None:
            return
        if item.checkState() is Qt.CheckState.Checked:
            self._selected_item_ids.add(item_id)
        else:
            self._selected_item_ids.discard(item_id)
        self.update_status()

    def select_visible_resources(self) -> None:
        for index in range(self.resource_list.count()):
            item = self.resource_list.item(index)
            if item is None:
                continue
            item.setCheckState(Qt.CheckState.Checked)

    def clear_visible_resources(self) -> None:
        for index in range(self.resource_list.count()):
            item = self.resource_list.item(index)
            if item is None:
                continue
            item.setCheckState(Qt.CheckState.Unchecked)

    def update_status(self) -> None:
        mode = self.filter_mode_combo.currentData()
        if mode is HarvestResourceFilterMode.INCLUDE and not self._selected_item_ids:
            self.status.setText("Select at least one resource, or switch back to All resources.")
            return
        if mode is HarvestResourceFilterMode.EXCLUDE and not self._selected_item_ids:
            self.status.setText("No excluded resources; all resources remain available.")
            return
        self.status.setText(f"{len(self._selected_item_ids)} resources selected for this filter.")

    def accept(self) -> None:
        if (
            self.filter_mode_combo.currentData() is HarvestResourceFilterMode.INCLUDE
            and not self._selected_item_ids
        ):
            self.update_status()
            return
        super().accept()
