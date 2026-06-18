import enum

from pydantic import BaseModel
from simnet.models.zzz.chronicle.hadal import ZZZHadalInfo
from simnet.models.zzz.diary import ZZZDiary
from simnet.models.zzz.chronicle.challenge import ZZZChallenge
from simnet.models.zzz.chronicle.challenge_mem import ZZZChallengeMem
from simnet.models.zzz.chronicle.holo_boss_detail import ZZZHoloBossDetail

from gram_core.services.history_data.models import HistoryData

__all__ = (
    "HistoryData",
    "HistoryDataTypeEnum",
    "HistoryDataAbyss",
    "HistoryDataChallengeMem",
    "HistoryDataLedger",
    "HistoryDataChallengeHadal",
    "HistoryDataChallengeHolo",
)


class HistoryDataTypeEnum(int, enum.Enum):
    ABYSS = 0  # 混沌回忆
    CHALLENGE_STORY = 1  # 虚构叙事
    LEDGER = 2  # 开拓月历
    CHALLENGE_BOSS = 3  # 末日幻影
    CHALLENGE_HOLO = 4  # 拟境湮灭战


class HistoryDataAbyss(BaseModel):
    abyss_data: ZZZChallenge

    @classmethod
    def from_data(cls, data: HistoryData) -> "HistoryDataAbyss":
        return cls.model_validate(data.data)


class HistoryDataChallengeMem(BaseModel):
    abyss_data: ZZZChallengeMem

    @classmethod
    def from_data(cls, data: HistoryData) -> "HistoryDataChallengeMem":
        return cls.model_validate(data.data)


class HistoryDataLedger(BaseModel):
    diary_data: ZZZDiary

    @classmethod
    def from_data(cls, data: HistoryData) -> "HistoryDataLedger":
        return cls.model_validate(data.data)


class HistoryDataChallengeHadal(BaseModel):
    abyss_data: ZZZHadalInfo

    @classmethod
    def from_data(cls, data: HistoryData) -> "HistoryDataChallengeHadal":
        return cls.model_validate(data.data)


class HistoryDataChallengeHolo(BaseModel):
    abyss_data: ZZZHoloBossDetail

    @classmethod
    def from_data(cls, data: HistoryData) -> "HistoryDataChallengeHolo":
        return cls.model_validate(data.data)
