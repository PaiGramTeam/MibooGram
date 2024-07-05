from core.base_service import BaseService
from modules.wiki.character import Character
from modules.wiki.weapon import Weapon
from modules.wiki.buddy import Buddy
from modules.wiki.raider import Raider
from modules.wiki.equipment_suit import EquipmentSuit
from utils.log import logger

__all__ = ["WikiService"]


class WikiService(BaseService):
    def __init__(self):
        self.character = Character()
        self.weapon = Weapon()
        self.buddy = Buddy()
        self.raider = Raider()
        self.equipment_suit = EquipmentSuit()

    async def initialize(self) -> None:
        logger.info("正在加载 Wiki 数据")
        try:
            await self.character.read()
            await self.weapon.read()
            await self.buddy.read()
            await self.raider.read()
            await self.equipment_suit.read()
        except Exception as e:
            logger.error("加载 Wiki 数据失败", exc_info=e)
        logger.info("加载 Wiki 数据完成")

    async def refresh_wiki(self) -> None:
        logger.info("正在重新获取Wiki")
        logger.info("正在重新获取角色信息")
        await self.character.refresh()
        logger.info("正在重新获取武器信息")
        await self.weapon.refresh()
        logger.info("正在重新获取邦布信息")
        await self.buddy.refresh()
        logger.info("正在重新获取攻略信息")
        await self.raider.refresh()
        logger.info("正在重新获取驱动盘信息")
        await self.equipment_suit.refresh()
        logger.info("刷新成功")
