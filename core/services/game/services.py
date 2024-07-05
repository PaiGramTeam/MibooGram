from core.base_service import BaseService
from core.services.game.cache import (
    GameCacheForAvatar,
    GameCacheForStrategy,
    GameCacheForBuddy,
    GameCacheForWeapon,
    GameCacheForEquipmentSuit,
)

__all__ = "GameCacheService"


class GameCacheService(BaseService):
    def __init__(
        self,
        avatar_cache: GameCacheForAvatar,
        strategy_cache: GameCacheForStrategy,
        buddy_cache: GameCacheForBuddy,
        weapon_cache: GameCacheForWeapon,
        equipment_suit_cache: GameCacheForEquipmentSuit,
    ):
        self.avatar_cache = avatar_cache
        self.strategy_cache = strategy_cache
        self.buddy_cache = buddy_cache
        self.weapon_cache = weapon_cache
        self.equipment_suit_cache = equipment_suit_cache

    async def get_avatar_cache(self, character_name: str) -> str:
        cache = await self.avatar_cache.get_file(character_name)
        if cache is not None:
            return cache.decode("utf-8")

    async def set_avatar_cache(self, character_name: str, file: str) -> None:
        await self.avatar_cache.set_file(character_name, file)

    async def get_strategy_cache(self, character_name: str) -> str:
        cache = await self.strategy_cache.get_file(character_name)
        if cache is not None:
            return cache.decode("utf-8")

    async def set_strategy_cache(self, character_name: str, file: str) -> None:
        await self.strategy_cache.set_file(character_name, file)

    async def get_buddy_cache(self, character_name: str) -> str:
        cache = await self.buddy_cache.get_file(character_name)
        if cache is not None:
            return cache.decode("utf-8")

    async def set_buddy_cache(self, character_name: str, file: str) -> None:
        await self.buddy_cache.set_file(character_name, file)

    async def get_weapon_cache(self, weapon_name: str) -> str:
        cache = await self.weapon_cache.get_file(weapon_name)
        if cache is not None:
            return cache.decode("utf-8")

    async def set_weapon_cache(self, weapon_name: str, file: str) -> None:
        await self.weapon_cache.set_file(weapon_name, file)

    async def get_equipment_suit_cache(self, relics_name: str) -> str:
        cache = await self.equipment_suit_cache.get_file(relics_name)
        if cache is not None:
            return cache.decode("utf-8")

    async def set_equipment_suit_cache(self, relics_name: str, file: str) -> None:
        await self.equipment_suit_cache.set_file(relics_name, file)
