from typing import Tuple, Optional

from simnet import ZZZClient
from simnet.models.zzz.calculator import ZZZCalculatorCharacterDetails

from gram_core.dependence.redisdb import RedisDB
from plugins.tools.genshin import GenshinHelper


class NeedClient(Exception):
    """无缓存，需要 StarRailClient"""


class PlayerDetailHelper:
    def __init__(self, helper: GenshinHelper, redis: RedisDB):
        self.helper = helper
        self.qname = "plugins:agent_detail"
        self.redis = redis.client
        self.expire = 15 * 60  # 15分钟

    async def set_characters_for_redis(
        self,
        uid: int,
        nickname: str,
        data: "ZZZCalculatorCharacterDetails",
    ) -> None:
        data_k = f"{self.qname}:{uid}:data"
        json_data = data.json(by_alias=True)
        await self.redis.set(data_k, json_data, ex=self.expire)

    async def del_characters_for_redis(
        self,
        uid: int,
    ) -> None:
        data_k = f"{self.qname}:{uid}:data"
        await self.redis.delete(data_k)

    async def get_characters_for_redis(
        self,
        uid: int,
    ) -> Tuple[Optional[str], Optional["ZZZCalculatorCharacterDetails"]]:
        data_k = f"{self.qname}:{uid}:data"
        data_v = await self.redis.get(data_k)
        if data_v is None:
            return None, None
        json_data = str(data_v, encoding="utf-8")
        return "", ZZZCalculatorCharacterDetails.parse_raw(json_data)

    async def get_characters(
        self, uid: int, client: "ZZZClient" = None
    ) -> Tuple[Optional[str], Optional["ZZZCalculatorCharacterDetails"]]:
        nickname, data = await self.get_characters_for_redis(uid)
        if nickname is None or data is None:
            if not client:
                raise NeedClient
            data1 = await client.get_zzz_characters()
            cids = [i.id for i in data1.characters]
            data = await client.get_zzz_character_info(cids)
            await self.set_characters_for_redis(client.player_id, "", data)
        return nickname, data
