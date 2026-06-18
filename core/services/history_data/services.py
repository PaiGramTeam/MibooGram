import datetime
from typing import List

from simnet.models.zzz.chronicle.hadal import ZZZHadalInfo
from simnet.models.zzz.diary import ZZZDiary
from simnet.models.zzz.chronicle.challenge import ZZZChallenge
from simnet.models.zzz.chronicle.challenge_mem import ZZZChallengeMem
from simnet.models.zzz.chronicle.holo_boss_detail import ZZZHoloBossDetail

from core.services.history_data.models import (
    HistoryData,
    HistoryDataTypeEnum,
    HistoryDataAbyss,
    HistoryDataLedger,
    HistoryDataChallengeMem,
    HistoryDataChallengeHadal,
    HistoryDataChallengeHolo,
)
from gram_core.base_service import BaseService
from gram_core.services.history_data.services import HistoryDataBaseServices

try:
    import ujson as jsonlib
except ImportError:
    import json as jsonlib


__all__ = (
    "HistoryDataBaseServices",
    "HistoryDataAbyssServices",
    "HistoryDataChallengeMemServices",
    "HistoryDataLedgerServices",
    "HistoryDataChallengeHadalServices",
    "HistoryDataChallengeHoloServices",
)


class HistoryDataAbyssServices(BaseService, HistoryDataBaseServices):
    DATA_TYPE = HistoryDataTypeEnum.ABYSS.value

    @staticmethod
    def exists_data(data: HistoryData, old_data: List[HistoryData]) -> bool:
        floors = data.data.get("abyss_data", {}).get("all_floor_detail")
        return any(d.data.get("abyss_data", {}).get("all_floor_detail") == floors for d in old_data)

    @staticmethod
    def create(user_id: int, abyss_data: ZZZChallenge):
        data = HistoryDataAbyss(abyss_data=abyss_data)
        json_data = data.model_dump_json(by_alias=True)
        return HistoryData(
            user_id=user_id,
            data_id=abyss_data.season,
            time_created=datetime.datetime.now(),
            type=HistoryDataAbyssServices.DATA_TYPE,
            data=jsonlib.loads(json_data),
        )


class HistoryDataChallengeMemServices(BaseService, HistoryDataBaseServices):
    DATA_TYPE = HistoryDataTypeEnum.CHALLENGE_BOSS.value

    @staticmethod
    def exists_data(data: HistoryData, old_data: List[HistoryData]) -> bool:
        floors = data.data.get("abyss_data", {}).get("list")
        return any(d.data.get("abyss_data", {}).get("list") == floors for d in old_data)

    @staticmethod
    def create(user_id: int, abyss_data: ZZZChallengeMem):
        data = HistoryDataChallengeMem(abyss_data=abyss_data)
        json_data = data.model_dump_json(by_alias=True)
        return HistoryData(
            user_id=user_id,
            data_id=abyss_data.season,
            time_created=datetime.datetime.now(),
            type=HistoryDataChallengeMemServices.DATA_TYPE,
            data=jsonlib.loads(json_data),
        )


class HistoryDataLedgerServices(BaseService, HistoryDataBaseServices):
    DATA_TYPE = HistoryDataTypeEnum.LEDGER.value

    @staticmethod
    def create(user_id: int, diary_data: ZZZDiary):
        data = HistoryDataLedger(diary_data=diary_data)
        json_data = data.model_dump_json(by_alias=True)
        return HistoryData(
            user_id=user_id,
            data_id=diary_data.data_id,
            time_created=datetime.datetime.now(),
            type=HistoryDataLedgerServices.DATA_TYPE,
            data=jsonlib.loads(json_data),
        )


class HistoryDataChallengeHadalServices(BaseService, HistoryDataBaseServices):
    DATA_TYPE = HistoryDataTypeEnum.CHALLENGE_STORY.value

    @staticmethod
    def exists_data(data: HistoryData, old_data: List[HistoryData]) -> bool:

        def _get_data(_data: HistoryData):
            info = _data.data.get("abyss_data", {}).get("hadal_info_v2", {})
            four = info.get("fourth_layer_detail", {}).get("layer_challenge_info_list", [])
            fif = info.get("fitfh_layer_detail", {}).get("layer_challenge_info_list", [])
            _avatars = []
            for layer in (four, fif):
                for floor_data in layer:
                    for avatar in floor_data.get("avatar_list", []):
                        _avatars.append(avatar["id"])
            return _avatars

        avatars = _get_data(data)
        return any(_get_data(d) == avatars for d in old_data)

    @staticmethod
    def create(user_id: int, abyss_data: ZZZHadalInfo):
        data = HistoryDataChallengeHadal(abyss_data=abyss_data)
        json_data = data.model_dump_json(by_alias=True)
        return HistoryData(
            user_id=user_id,
            data_id=abyss_data.hadal_info_v2.season,
            time_created=datetime.datetime.now(),
            type=HistoryDataChallengeHadalServices.DATA_TYPE,
            data=jsonlib.loads(json_data),
        )


class HistoryDataChallengeHoloServices(BaseService, HistoryDataBaseServices):
    DATA_TYPE = HistoryDataTypeEnum.CHALLENGE_HOLO.value

    @staticmethod
    def exists_data(data: HistoryData, old_data: List[HistoryData]) -> bool:

        def _get_data(_data: HistoryData):
            info = _data.data.get("abyss_data", {}).get("list")
            _avatars = []
            for i in info:
                _avatars.extend(i.get("avatar_list", []))
            return _avatars

        avatars = _get_data(data)
        return any(_get_data(d) == avatars for d in old_data)

    @staticmethod
    def create(user_id: int, abyss_data: ZZZHoloBossDetail):
        data = HistoryDataChallengeHolo(abyss_data=abyss_data)
        json_data = data.model_dump_json(by_alias=True)
        return HistoryData(
            user_id=user_id,
            data_id=abyss_data.season,
            time_created=datetime.datetime.now(),
            type=HistoryDataChallengeHoloServices.DATA_TYPE,
            data=jsonlib.loads(json_data),
        )
