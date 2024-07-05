from typing import List

from pydantic import BaseModel

from .enums import ZZZElementType, ZZZSpeciality, ZZZRank


class Avatar(BaseModel, frozen=False):
    id: int
    """ 角色ID """
    name: str
    """ 中文名称 """
    name_en: str
    """ 英文名称 """
    name_full: str
    """ 中文全称 """
    name_short: str
    """ 英文简称 """
    rank: ZZZRank = ZZZRank.NULL
    """ 星级 """
    element: ZZZElementType
    """ 元素 """
    speciality: ZZZSpeciality
    """ 特性 """
    icon: List[str] = ["", "", ""]
    """ 图标 """

    @property
    def icon_(self) -> str:
        return self.icon[0]

    @property
    def normal(self) -> str:
        return self.icon[1]

    @property
    def gacha(self) -> str:
        return self.icon[2]
