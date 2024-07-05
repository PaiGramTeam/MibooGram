from pydantic import BaseModel

from .enums import ZZZRank


class EquipmentSuit(BaseModel):
    id: int
    """驱动盘套装ID"""
    name: str
    """套装名称"""
    name_en: str
    """英文套装名称"""
    icon: str = ""
    """套装图标"""
    desc_2: str
    """2套描述"""
    desc_4: str
    """4套描述"""
    story: str
    """套装故事"""
    rank: ZZZRank = ZZZRank.NULL
    """ 星级 """
