from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel
from simnet import ZZZClient

from core.plugin import Plugin
from core.services.players.models import PlayersDataBase as Player
from core.services.players.services import PlayerInfoService, PlayersService
from gram_core.dependence.redisdb import RedisDB
from gram_core.services.players.models import ExtraPlayerInfo
from plugins.tools.genshin import GenshinHelper
from utils.const import RESOURCE_DIR
from utils.log import logger


class PlayerAvatarInfo(BaseModel, frozen=False):
    player_id: int
    name_card: str
    avatar: str
    nickname: str
    level: int


class PlayerInfoSystem(Plugin):
    def __init__(
        self,
        player_service: PlayersService = None,
        player_info_service: PlayerInfoService = None,
        helper: GenshinHelper = None,
        redis: RedisDB = None,
    ) -> None:
        self.player_service = player_service
        self.player_info_service = player_info_service
        self.helper = helper
        self.cache = redis.client
        self.qname = "players_info_avatar"
        self.ttl = 1 * 60 * 60  # 1小时

    async def get_form_cache(self, player_id: int) -> Optional[PlayerAvatarInfo]:
        qname = f"{self.qname}:{player_id}"
        data = await self.cache.get(qname)
        if data is None:
            return None
        json_data = str(data, encoding="utf-8")
        return PlayerAvatarInfo.parse_raw(json_data)

    async def set_form_cache(self, player: PlayerAvatarInfo):
        qname = f"{self.qname}:{player.player_id}"
        await self.cache.set(qname, player.json(), ex=self.ttl)

    @staticmethod
    def get_base_avatar_info(player_id: int, user_name: str) -> PlayerAvatarInfo:
        res = RESOURCE_DIR / "img"
        return PlayerAvatarInfo(
            player_id=player_id,
            name_card=(res / "home.png").as_uri(),
            avatar=(res / "avatar.png").as_uri(),
            nickname=user_name,
            level=0,
        )

    async def update_player_info(self, player: "Player", base_info: "PlayerAvatarInfo"):
        player_info = await self.player_info_service.get_form_sql(player)
        if player_info is not None and player_info.create_time is not None:
            player_info.nickname = base_info.nickname
            ex = player_info.extra_data
            player_info.extra_data = ExtraPlayerInfo()
            if ex is not None:
                ex.copy_to(player_info.extra_data)
            player_info.extra_data.level = base_info.level
            player_info.extra_data.avatar = base_info.avatar
            await self.player_info_service.update(player_info)

    async def get_player_info_by_cookie(self, player: "Player", user_name: str) -> PlayerAvatarInfo:
        base_info = self.get_base_avatar_info(player.player_id, user_name)
        try:
            async with self.helper.genshin(player.user_id, player_id=player.player_id) as client:
                client: "ZZZClient"
                record_card = await client.get_record_card()
                index = await client.get_zzz_user()
                if record_card is not None:
                    base_info.nickname = record_card.nickname
                    base_info.level = record_card.level
                if index is not None:
                    base_info.avatar = index.cur_head_icon_url
                if base_info.level:
                    await self.update_player_info(player, base_info)
        except Exception as e:
            logger.warning("卡片信息通过 cookie 请求失败 %s", str(e))
        return base_info

    async def get_player_info(self, player_id: int, user_name: str) -> PlayerAvatarInfo:
        cache = await self.get_form_cache(player_id)
        if cache is not None:
            return cache

        player = await self.player_service.get(None, player_id)
        base_info = self.get_base_avatar_info(player_id, user_name)
        if not player:
            return base_info
        player_info = await self.player_info_service.get(player)
        if player_info is None or player_info.create_time is None:
            return base_info
        expiration_time = datetime.now() - timedelta(hours=2)
        if (
            player_info.last_save_time is None
            or player_info.extra_data is None
            or player_info.last_save_time <= expiration_time
        ):
            base_info = await self.get_player_info_by_cookie(player, player_info.nickname)
        else:
            base_info.nickname = player_info.nickname or ""
            base_info.avatar = player_info.extra_data.avatar or base_info.avatar
            base_info.level = player_info.extra_data.level or 0

        await self.set_form_cache(base_info)
        return base_info

    async def get_theme_info(self, player_id: int) -> PlayerAvatarInfo:
        return await self.get_player_info(player_id, "")
