from enum import Enum, IntEnum


class ZZZElementType(IntEnum):
    """ZZZ element type."""

    NULL = 1
    """ 空 """
    PHYSICAL = 200
    """ 物理 """
    FIRE = 201
    """ 火 """
    ICE = 202
    """ 冰 """
    ELECTRIC = 203
    """ 电 """
    ETHER = 205
    """ 以太 """


class ZZZSpeciality(IntEnum):
    """ZZZ agent compatible speciality."""

    ATTACK = 1
    """ 强攻 """
    STUN = 2
    """ 击破 """
    ANOMALY = 3
    """ 异常 """
    SUPPORT = 4
    """ 支援 """
    DEFENSE = 5
    """ 防护 """


class ZZZRank(str, Enum):
    """ZZZ Rank"""

    S = "S"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    NULL = "NULL"

    @property
    def int(self):
        value_map = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1, "NULL": 0}
        return value_map[self.value]
