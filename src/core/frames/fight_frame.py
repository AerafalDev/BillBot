from dataclasses import dataclass

from DBDofusUnity.datas.protos.non_obf.game.character_pb2 import CharacterCharacteristicsEvent
from DBDofusUnity.datas.protos.non_obf.game.common_pb2 import (
    FightRemovableEffect,
    FightInvisibilityState,
)
from DBDofusUnity.datas.protos.non_obf.game.context_pb2 import ContextCreationEvent
from DBDofusUnity.datas.protos.non_obf.game.fight_pb2 import (
    FightEffectsEvent,
    FightJoinRunningEvent,
    FightRefreshCharacterStatsEvent,
    FightSynchronizeEvent,
    FightTurnEvent,
    FightTurnFinishRequest,
)
from DBDofusUnity.datas.protos.non_obf.game.fight_preparation_pb2 import (
    FightPlacementPossiblePositionsEvent,
)
from DBDofusUnity.datas.protos.non_obf.game.game_action_pb2 import (
    GameActionFightCastRequest,
    GameActionFightEvent,
)
from DBDofusUnity.datas.protos.non_obf.game.gamemap_pb2 import (
    FightMapInformationEvent,
    MapComplementaryInformationEvent,
)
from DBDofusUnity.datas.protos.non_obf.game.spell_pb2 import (
    SpellItem,
    SpellsEvent,
    SpellVariantActivationEvent,
)
from DBDofusUnity.dofus_unity_reader.data_center.data_reader import DataReader
from DBDofusUnity.dofus_unity_reader.game_constants.characteristic import CharacteristicEnum

from src.core.engine.fights.effect import ADD_STATE_ACTION_ID
from src.core.frames.frame import Frame


@dataclass
class FightFrame(Frame):
    def __post_init__(self):
        self.event_manager.on(
            FightPlacementPossiblePositionsEvent,
            self.on_fight_placement_position_request,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.on(
            SpellsEvent,
            self.on_spells_event,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.on(
            SpellVariantActivationEvent,
            self.on_spell_variant_activation_event,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.on(
            GameActionFightCastRequest,
            self.on_game_action_fight_cast_request,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.on(
            CharacterCharacteristicsEvent,
            self.on_character_characteristics_event,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.before(
            FightTurnFinishRequest,
            self.before_fight_turn_finish_request,
            originator=self,
        )
        self.event_manager.on(
            GameActionFightEvent,
            self.on_game_action_fight_event,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.on(
            FightSynchronizeEvent,
            self.on_fight_synchronize_event,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.on(
            FightEffectsEvent,
            self.on_fight_effects_event,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.on(
            FightJoinRunningEvent,
            self.on_fight_join_running_event,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.on(
            FightRefreshCharacterStatsEvent,
            self.on_fight_refresh_character_stats_event,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.on(
            FightMapInformationEvent,
            self.on_fight_map_information_event,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.on(
            FightTurnEvent,
            self.on_fight_turn_event,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.on(
            MapComplementaryInformationEvent,
            self.on_map_complementary_information_event,
            originator=self,
            priority=self.priority,
        )
        self.event_manager.on(
            ContextCreationEvent,
            self.on_context_creation_event,
            originator=self,
            priority=self.priority,
        )

    def on_context_creation_event(self, msg: ContextCreationEvent):
        self.game_state.fight.in_fight = msg.context == ContextCreationEvent.GameContext.FIGHT

    def on_fight_placement_position_request(self, msg: FightPlacementPossiblePositionsEvent):
        if self.game_state.map.map_point.cell_id in msg.starting_positions.challengers_positions:
            self.game_state.fight.fight_placement_possible_positions = list(
                msg.starting_positions.challengers_positions
            )
        else:
            self.game_state.fight.fight_placement_possible_positions = list(
                msg.starting_positions.defenders_positions
            )

    def on_spells_event(self, message: SpellsEvent):
        self.game_state.fight.spells = list(message.human_spells)

    def on_spell_variant_activation_event(self, message: SpellVariantActivationEvent):
        if not message.effective:
            return
        spells = self.game_state.fight.spells
        if any(spell.spell_id == message.spell_id for spell in spells):
            return
        first_spell_lvl = DataReader().spell_lvl_by_spell_id[message.spell_id][0]
        self.game_state.fight.spells = [
            *spells,
            SpellItem(spell_id=message.spell_id, spell_level=first_spell_lvl.grade, available=True),
        ]

    def on_game_action_fight_cast_request(self, message: GameActionFightCastRequest):
        self.game_state.fight.count_casted_by_spell_id_on_current_turn[message.spell_id] = (
            self.game_state.fight.count_casted_by_spell_id_on_current_turn.get(message.spell_id, 0) + 1
        )
        target_actor = self.game_state.entity.get_first_actor_on_cell_id(message.cell)
        if target_actor is not None:
            target_key = (message.spell_id, target_actor.actor_id)
            self.game_state.fight.count_casted_by_spell_id_and_target_id[target_key] = (
                self.game_state.fight.count_casted_by_spell_id_and_target_id.get(target_key, 0) + 1
            )
        self.game_state.fight.cast_turn_by_spell_id[message.spell_id] = self.game_state.fight.fight_turn

    def on_character_characteristics_event(self, message: CharacterCharacteristicsEvent):
        self.game_state.fight.modifier_by_type_and_spell_id.clear()
        for spell_modifier in message.stats.spell_modifiers:
            self.game_state.fight.modifier_by_type_and_spell_id[
                (spell_modifier.spell_id, spell_modifier.modifier_type)
            ] = spell_modifier

        for stat in message.stats.characteristics:
            self.game_state.fight.update_characteristic(stat)
        hp_before = self.game_state.fight.life_point
        self.game_state.fight.sync_life_points_from_characteristics()
        self._log_life_resync("CharacterCharacteristicsEvent", hp_before)

    def before_fight_turn_finish_request(self, msg: FightTurnFinishRequest) -> FightTurnFinishRequest | None:
        if self.is_playing_event.is_set():
            return None
        return msg

    def on_game_action_fight_event(self, msg: GameActionFightEvent):
        if msg.HasField("mark_cells"):
            self.game_state.fight.set_fight_mark(msg.mark_cells.mark)
        if msg.HasField("unmark_cells"):
            self.game_state.fight.remove_fight_mark(msg.unmark_cells.mark_id)
        if msg.HasField("trigger_glyph_trap"):
            self.game_state.fight.remove_fight_mark(msg.trigger_glyph_trap.mark_id)

        if msg.HasField("death") and (msg.death.target_id == self.game_state.player.character_id):
            hp_before = self.game_state.fight.life_point
            self.logger.info(
                "Player HP death event: "
                f"hp_before={hp_before}, source_id={msg.source_id}, "
                f"death_source_id={msg.death.source_id}, target_id={msg.death.target_id}"
            )
            self.game_state.fight.life_point = 0
            self.logger.info("Player HP death applied: hp_after=0")

        if msg.HasField("life_points_gain"):
            if msg.life_points_gain.target_id == self.game_state.player.character_id:
                hp_before = self.game_state.fight.life_point
                hp_after = hp_before + msg.life_points_gain.delta
                self.logger.info(
                    "Player HP gain event: "
                    f"hp_before={hp_before}, delta={msg.life_points_gain.delta}, "
                    f"hp_after={hp_after}, source_id={msg.source_id}, "
                    f"target_id={msg.life_points_gain.target_id}"
                )
                self.game_state.fight.life_point = hp_after
            else:
                if msg.life_points_gain.target_id not in self.game_state.entity.actor_fight_by_id:
                    self.logger.error(
                        "Non-player HP gain targets missing fight actor: "
                        f"target_id={msg.life_points_gain.target_id}, "
                        f"delta={msg.life_points_gain.delta}, source_id={msg.source_id}"
                    )
                self.game_state.entity.actor_fight_by_id[
                    msg.life_points_gain.target_id
                ].life_point += msg.life_points_gain.delta

        if msg.HasField("life_points_lost"):
            if msg.life_points_lost.target_id == self.game_state.player.character_id:
                hp_before = self.game_state.fight.life_point
                hp_after = max(hp_before - msg.life_points_lost.loss, 0)
                log_message = (
                    "Player HP loss event: "
                    f"hp_before={hp_before}, loss={msg.life_points_lost.loss}, "
                    f"shield_loss={msg.life_points_lost.shield_loss}, "
                    f"permanent_damages={msg.life_points_lost.permanent_damages}, "
                    f"element_id={msg.life_points_lost.element_id}, "
                    f"hp_after={hp_after}, source_id={msg.source_id}, "
                    f"target_id={msg.life_points_lost.target_id}"
                )
                if msg.life_points_lost.loss > hp_before:
                    self.logger.info(f"{log_message} (fatal damage clamped to 0 HP)")
                else:
                    self.logger.info(log_message)
                self.game_state.fight.life_point = hp_after
            else:
                if msg.life_points_lost.target_id not in self.game_state.entity.actor_fight_by_id:
                    self.logger.error(
                        "Non-player HP loss targets missing fight actor: "
                        f"target_id={msg.life_points_lost.target_id}, "
                        f"loss={msg.life_points_lost.loss}, source_id={msg.source_id}"
                    )
                actor_fight = self.game_state.entity.actor_fight_by_id[msg.life_points_lost.target_id]
                actor_fight.life_point = max(
                    actor_fight.life_point - msg.life_points_lost.loss,
                    0,
                )

        player_id = self.game_state.player.character_id

        if msg.HasField("spell_remove"):
            removal = msg.spell_remove
            complement = removal.WhichOneof("complement")
            if removal.target_id == player_id:
                if complement == "effect_remove":
                    effect_uid = removal.effect_remove.effect
                    self.game_state.fight.own_spell_id_by_effect_uid.pop(effect_uid, None)
                    self.game_state.fight.own_state_id_by_effect_uid.pop(effect_uid, None)
                elif complement == "spell_id":
                    stale_uids = [
                        uid
                        for uid, spell_id in self.game_state.fight.own_spell_id_by_effect_uid.items()
                        if spell_id == removal.spell_id
                    ]
                    for uid in stale_uids:
                        del self.game_state.fight.own_spell_id_by_effect_uid[uid]
                        self.game_state.fight.own_state_id_by_effect_uid.pop(uid, None)
            elif complement == "effect_remove":
                self.game_state.entity.remove_fight_actor_effect(
                    removal.target_id, removal.effect_remove.effect
                )
            elif complement == "spell_id":
                self.game_state.entity.remove_fight_actor_spell_states(
                    removal.target_id, removal.spell_id
                )

        if msg.HasField("removable_effect"):
            self._track_removable_effect(msg.removable_effect.effect)

        if msg.HasField("invisibility") and msg.invisibility.target_id != player_id:
            self.game_state.entity.set_fight_actor_invisibility(
                msg.invisibility.target_id, msg.invisibility.invisibility_state
            )

        if msg.HasField("invisible_detected") and msg.invisible_detected.target_id != player_id:
            self.game_state.entity.set_fight_actor_invisibility(
                msg.invisible_detected.target_id, FightInvisibilityState.DETECTED
            )

    def on_fight_synchronize_event(self, msg: FightSynchronizeEvent):
        player_id = self.game_state.player.character_id
        player_fighter = next(actor for actor in msg.fighters if actor.actor_id == player_id)
        for characteristic in player_fighter.actor_information.fighter.stats.characteristics:
            self.game_state.fight.update_characteristic(characteristic)
        hp_before = self.game_state.fight.life_point
        self.game_state.fight.sync_life_points_from_characteristics()
        self._log_life_resync("FightSynchronizeEvent", hp_before)

    def on_fight_effects_event(self, msg: FightEffectsEvent) -> None:
        self._track_removable_effect(msg.effect.effect)

    def on_fight_join_running_event(self, msg: FightJoinRunningEvent) -> None:
        self.game_state.fight.set_fight_marks(msg.marks)
        for effect in msg.effects:
            self._track_removable_effect(effect.effect)

    def _track_removable_effect(self, active_effect: FightRemovableEffect) -> None:
        player_id = self.game_state.player.character_id
        if active_effect.target_id == player_id:
            self.game_state.fight.own_spell_id_by_effect_uid[active_effect.uid] = active_effect.spell_id
        if active_effect.effect_id != ADD_STATE_ACTION_ID:
            return

        state_id = DataReader().state_id_by_spell_and_effect_uid.get(
            (active_effect.spell_id, active_effect.uid)
        )
        if state_id is None:
            matching_state_ids = {
                effect.value
                for spell_lvl in DataReader().spell_lvl_by_spell_id.get(active_effect.spell_id, [])
                for effect in (*spell_lvl.effects, *spell_lvl.criticalEffect)
                if effect.effectId == ADD_STATE_ACTION_ID and effect.value > 0
            }
            if len(matching_state_ids) == 1:
                state_id = next(iter(matching_state_ids))
        if state_id is None:
            return
        if active_effect.target_id == player_id:
            self.game_state.fight.own_state_id_by_effect_uid[active_effect.uid] = state_id
        else:
            self.game_state.entity.set_fight_actor_state(
                active_effect.target_id,
                active_effect.uid,
                state_id,
                active_effect.spell_id,
            )

    def on_fight_refresh_character_stats_event(self, msg: FightRefreshCharacterStatsEvent):
        if self.game_state.player.character_id != msg.fighter_id:
            return
        has_life_stat = False
        for characteristic in msg.stats.characteristics:
            self.game_state.fight.update_characteristic(characteristic)
            if characteristic.characteristic_id in _LIFE_CHARACTERISTIC_IDS:
                has_life_stat = True
        if not has_life_stat:
            return
        if not self.game_state.fight.can_sync_life_points_from_characteristics():
            return
        hp_before = self.game_state.fight.life_point
        self.game_state.fight.sync_life_points_from_characteristics()
        self._log_life_resync("FightRefreshCharacterStatsEvent", hp_before)

    def _log_life_resync(self, source_event: str, hp_before: int) -> None:
        life_points = self.game_state.fight.get_stat_by_id(CharacteristicEnum.LIFE_POINTS)
        vitality = self.game_state.fight.get_stat_by_id(CharacteristicEnum.VITALITY)
        current_life_delta = self.game_state.fight.get_stat_by_id(CharacteristicEnum.CUR_LIFE)
        self.logger.info(
            "Player HP resync: "
            f"source={source_event}, hp_before={hp_before}, "
            f"life_points={life_points}, vitality={vitality}, "
            f"cur_life={current_life_delta}, "
            f"hp_after={self.game_state.fight.life_point}, "
            f"max_hp_after={self.game_state.fight.max_life_point}"
        )

    def on_fight_map_information_event(self, msg: FightMapInformationEvent):
        self.game_state.fight.count_casted_by_spell_id_on_current_turn.clear()
        self.game_state.fight.count_casted_by_spell_id_and_target_id.clear()
        self.game_state.fight.cast_turn_by_spell_id.clear()
        self.game_state.fight.modifier_by_type_and_spell_id.clear()
        self.logger.debug("Fight start: cleared per-fight cooldown/cast tracking")

    def on_fight_turn_event(self, msg: FightTurnEvent):
        self.game_state.fight.fight_placement_possible_positions.clear()
        self.game_state.fight.invisible_enemy_cell_ids.clear()
        if msg.character_id == self.game_state.player.character_id:
            self.game_state.fight.count_casted_by_spell_id_on_current_turn.clear()
            self.game_state.fight.count_casted_by_spell_id_and_target_id.clear()
            self.game_state.fight.is_our_turn = True
            self.game_state.fight.fight_turn += 1
        else:
            self.game_state.fight.count_casted_by_spell_id_on_current_turn.clear()
            self.game_state.fight.count_casted_by_spell_id_and_target_id.clear()
            self.game_state.fight.is_our_turn = False

    def on_map_complementary_information_event(self, msg: MapComplementaryInformationEvent):
        self.game_state.fight.modifier_by_type_and_spell_id.clear()
        self.game_state.fight.count_casted_by_spell_id_on_current_turn.clear()
        self.game_state.fight.count_casted_by_spell_id_and_target_id.clear()
        self.game_state.fight.in_fight = False
        self.game_state.fight.fight_turn = 0
        self.game_state.fight.is_our_turn = False
        self.game_state.fight.fight_placement_possible_positions.clear()

_LIFE_CHARACTERISTIC_IDS = {
    CharacteristicEnum.LIFE_POINTS,
    CharacteristicEnum.VITALITY,
    CharacteristicEnum.CUR_LIFE,
}
