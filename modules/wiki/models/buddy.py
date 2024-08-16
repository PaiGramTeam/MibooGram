from pydantic import BaseModel

from .enums import ZZZRank


class Buddy(BaseModel):
    id: int
    """"邦布ID"""
    name: str
    """名称"""
    name_en: str
    """英文名称"""
    icon: str = ""
    """图标"""
    square: str = ""
    """方形图标"""
    rank: ZZZRank = ZZZRank.NULL
    """ 星级 """

    @property
    def webp(self) -> str:
        return self.icon if self.icon.endswith("webp") else ""

    @property
    def png(self) -> str:
        return self.icon if self.icon.endswith("png") else ""
