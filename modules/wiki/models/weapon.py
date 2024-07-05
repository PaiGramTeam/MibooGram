from pydantic import BaseModel

from .enums import ZZZRank


class Weapon(BaseModel):
    id: int
    """"武器ID"""
    name: str
    """名称"""
    name_en: str
    """英文名称"""
    description: str
    """描述"""
    icon: str = ""
    """图标"""
    rank: ZZZRank
    """稀有度"""
