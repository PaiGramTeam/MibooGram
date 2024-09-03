from __future__ import annotations

import functools
from typing import List

# noinspection SpellCheckingInspection
roles = {
    2011: ["哲", "Wise", "wise", "哲"],
    2021: ["铃", "Belle", "belle", "铃"],
    1011: ["安比", "Anby", "anbi", "安比·德玛拉"],
    1021: ["猫又", "Nekomata", "tsubaki", "猫宫 又奈"],
    1031: ["妮可", "Nicole", "nicole", "妮可·德玛拉"],
    1041: ["「11号」", "Soldier 11", "longinus", "「11号」", "11号"],
    1061: ["可琳", "Corin", "corin", "可琳·威克斯"],
    1081: ["比利", "Billy", "billy", "比利·奇德"],
    1091: ["雅", "Miyabi", "unagi", "星见 雅"],
    1101: ["珂蕾妲", "Koleda", "koleda", "珂蕾妲·贝洛伯格"],
    1111: ["安东", "Anton", "anton", "安东·伊万诺夫"],
    1121: ["本", "Ben", "ben", "本·比格"],
    1131: ["苍角", "Soukaku", "aokaku", "苍角"],
    1141: ["莱卡恩", "Lycaon", "lycaon", "冯·莱卡恩"],
    1151: ["露西", "Lucy", "lucy", "露西亚娜·德·蒙特夫"],
    1161: ["莱特", "Lighter", "lighter", "莱特"],
    1181: ["格莉丝", "Grace", "lisa", "格莉丝·霍华德"],
    1191: ["艾莲", "Ellen", "ellen", "艾莲·乔"],
    1201: ["悠真", "Harumasa", "harumasa", "浅羽 悠真"],
    1211: ["丽娜", "Rina", "rina", "亚历山德丽娜·莎芭丝缇安"],
    1221: ["柳", "Yanagi", "yanagi", "月城 柳"],
    1241: ["朱鸢", "Zhu Yuan", "ZhuYuan", "朱鸢"],
    1251: ["青衣", "QingYi", "qingyi", "青衣"],
    1261: ["简", "Jane", "jane", "简"],
    1271: ["赛斯", "Seth", "seth", "赛斯·洛威尔"],
    1281: ["派派", "Piper", "clara", "派派·韦尔"],
}
not_real_roles = [1091, 1161, 1201, 1221]
weapons = {
    12001: ["「月相」-望"],
    12002: ["「月相」-晦"],
    12003: ["「月相」-朔"],
    12004: ["「残响」-Ⅰ型"],
    12005: ["「残响」-Ⅱ型"],
    12006: ["「残响」-Ⅲ型"],
    12007: ["「湍流」-铳型"],
    12008: ["「湍流」-矢型"],
    12009: ["「湍流」-斧型"],
    12010: ["「电磁暴」-壹式"],
    12011: ["「电磁暴」-贰式"],
    12012: ["「电磁暴」-叁式"],
    12013: ["「恒等式」-本格"],
    12014: ["「恒等式」-变格"],
    13001: ["街头巨星"],
    13002: ["时光切片"],
    13003: ["雨林饕客"],
    13004: ["星徽引擎"],
    13005: ["人为刀俎"],
    13006: ["贵重骨核"],
    13007: ["正版变身器"],
    13008: ["双生泣星"],
    13009: ["触电唇彩"],
    13010: ["兔能环"],
    13011: ["春日融融"],
    13013: ["鎏金花信"],
    13101: ["德玛拉电池Ⅱ型"],
    13103: ["聚宝箱"],
    13106: ["家政员"],
    13108: ["仿制星徽引擎"],
    13111: ["旋钻机-赤轴"],
    13112: ["比格气缸"],
    13113: ["含羞恶面"],
    13115: ["好斗的阿炮"],
    13127: ["维序者-特化型", "维序者·特化型"],
    13128: ["轰鸣座驾"],
    14001: ["加农转子"],
    14002: ["逍遥游球"],
    14003: ["左轮转子"],
    14102: ["钢铁肉垫"],
    14104: ["硫磺石"],
    14110: ["燃狱齿轮"],
    14114: ["拘缚者"],
    14118: ["嵌合编译器"],
    14119: ["深海访客"],
    14121: ["啜泣摇篮"],
    14123: ["玉壶青冰"],
    14124: ["防暴者Ⅵ型", "防暴者VI型"],
    14126: ["淬锋钳刺"],
}
buddy = {
    50001: ["伊埃斯"],
    53001: ["企鹅布"],
    53002: ["招财布"],
    53003: ["寻宝布"],
    53004: ["扑击布"],
    53005: ["纸壳布"],
    53006: ["纸袋布"],
    53007: ["泪眼布"],
    53008: ["果核布"],
    53009: ["飞靶布"],
    53010: ["电击布"],
    53011: ["磁力布"],
    53012: ["气压布"],
    54001: ["鲨牙布"],
    54002: ["阿全"],
    54003: ["恶魔布"],
    54004: ["巴特勒"],
    54005: ["艾米莉安"],
    54006: ["飚速布"],
    54008: ["插头布"],
    54009: ["共鸣布"],
    54012: ["阿崔巡查"],
    54013: ["左轮布"],
}


# noinspection PyPep8Naming
@functools.lru_cache()
def roleToName(shortname: str) -> str:
    """将角色昵称转为正式名"""
    shortname = str.casefold(shortname)  # 忽略大小写
    return next((value[0] for value in roles.values() for name in value if name == shortname), shortname)


# noinspection PyPep8Naming
@functools.lru_cache()
def roleToId(name: str) -> int | None:
    """获取角色ID"""
    name = str.casefold(name)
    return next((key for key, value in roles.items() for n in value if n == name), None)


# noinspection PyPep8Naming
@functools.lru_cache()
def idToRole(aid: int) -> str | None:
    """获取角色名"""
    return roles.get(aid, [None])[0]


# noinspection PyPep8Naming
@functools.lru_cache()
def weaponToName(shortname: str) -> str:
    """将武器昵称转为正式名"""
    shortname = str.casefold(shortname)  # 忽略大小写
    return next((value[0] for value in weapons.values() for name in value if name == shortname), shortname)


# noinspection PyPep8Naming
@functools.lru_cache()
def weaponToId(name: str) -> int | None:
    """获取武器ID"""
    new_name = str.casefold(name)
    f1 = next((key for key, value in weapons.items() for n in value if n == new_name), None)
    return f1 or next((key for key, value in weapons.items() for n in value if n == name), None)


# noinspection PyPep8Naming
@functools.lru_cache()
def idToWeapon(wid: int) -> str | None:
    """获取武器名"""
    return weapons.get(wid, [None])[0]


# noinspection PyPep8Naming
@functools.lru_cache()
def buddyToName(shortname: str) -> str:
    """将邦布昵称转为正式名"""
    shortname = str.casefold(shortname)  # 忽略大小写
    return next((value[0] for value in buddy.values() for name in value if name == shortname), shortname)


# noinspection PyPep8Naming
@functools.lru_cache()
def buddyToId(name: str) -> int | None:
    """获取邦布ID"""
    name = str.casefold(name)
    return next((key for key, value in buddy.items() for n in value if n == name), None)


# noinspection PyPep8Naming
@functools.lru_cache()
def idToBuddy(wid: int) -> str | None:
    """获取邦布名"""
    return buddy.get(wid, [None])[0]


# noinspection PyPep8Naming
@functools.lru_cache()
def roleToTag(role_name: str) -> List[str]:
    """通过角色名获取TAG"""
    role_name = str.casefold(role_name)
    return next((value for value in roles.values() if value[0] == role_name), [role_name])


@functools.lru_cache()
def weaponToTag(name: str) -> List[str]:
    """通过光锥名获取TAG"""
    name = str.casefold(name)
    return next((value for value in weapons.values() if value[0] == name), [name])


@functools.lru_cache()
def buddyToTag(name: str) -> List[str]:
    """通过邦布名获取TAG"""
    name = str.casefold(name)
    return next((value for value in buddy.values() if value[0] == name), [name])
