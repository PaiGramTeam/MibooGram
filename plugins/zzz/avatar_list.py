import asyncio
import math
from typing import List, Optional, TYPE_CHECKING, Dict, Union, Tuple, Any

from arkowrapper import ArkoWrapper
from pydantic import BaseModel
from simnet.models.zzz.calculator import ZZZCalculatorCharacter
from simnet.models.zzz.character import ZZZPartialCharacter
from telegram.constants import ChatAction
from telegram.ext import filters

from core.dependence.assets import AssetsService, AssetsCouldNotFound
from core.plugin import Plugin, handler
from core.services.cookies import CookiesService
from core.services.template.models import FileType
from core.services.template.services import TemplateService
from core.services.wiki.services import WikiService
from gram_core.plugin.methods.inline_use_data import IInlineUseData
from gram_core.services.template.models import RenderGroupResult
from plugins.tools.genshin import GenshinHelper, CharacterDetails
from utils.const import RESOURCE_DIR
from utils.log import logger
from utils.uid import mask_number

if TYPE_CHECKING:
    from simnet import ZZZClient
    from telegram.ext import ContextTypes
    from telegram import Update
    from gram_core.services.template.models import RenderResult

MAX_AVATAR_COUNT = 40


class EquipmentData(BaseModel):
    id: int
    name: str
    level: int
    eidolon: int
    rarity: int
    icon: str


class SkillData(BaseModel):
    id: int
    level: int
    max_level: int


class AvatarData(BaseModel):
    id: int
    name: str
    level: int
    eidolon: int
    rarity: int
    icon: str = ""
    skills: List[SkillData]
    equipment: Optional[EquipmentData] = None


class AvatarListPlugin(Plugin):
    """练度统计"""

    def __init__(
        self,
        cookies_service: CookiesService = None,
        assets_service: AssetsService = None,
        template_service: TemplateService = None,
        wiki_service: WikiService = None,
        helper: GenshinHelper = None,
        character_details: CharacterDetails = None,
    ) -> None:
        self.cookies_service = cookies_service
        self.assets_service = assets_service
        self.template_service = template_service
        self.wiki_service = wiki_service
        self.helper = helper
        self.character_details = character_details

    async def get_avatar_data(self, character_id: int, client: "ZZZClient") -> Optional["ZZZCalculatorCharacter"]:
        return await self.character_details.get_character_details(client, character_id)

    @staticmethod
    async def get_avatars_data(client: "ZZZClient") -> List["ZZZPartialCharacter"]:
        task_info_results = (await client.get_zzz_characters()).characters

        return sorted(
            list(filter(lambda x: x, task_info_results)),
            key=lambda x: (
                x.level,
                x.rarity,
                x.rank,
            ),
            reverse=True,
        )

    async def get_avatars_details(
        self, characters: List["ZZZPartialCharacter"], client: "ZZZClient"
    ) -> Dict[int, "ZZZCalculatorCharacter"]:
        async def _task(cid):
            return await self.get_avatar_data(cid, client)

        task_detail_results = await asyncio.gather(*[_task(character.id) for character in characters])

        return {character.id: detail for character, detail in zip(characters, task_detail_results)}

    @staticmethod
    def get_skill_data(character: Optional["ZZZCalculatorCharacter"]) -> List[SkillData]:
        if not character:
            return [SkillData(id=i, level=1, max_level=10) for i in range(1, 5)]
        return [SkillData(id=skill.skill_type, level=skill.level, max_level=10) for skill in character.skills]

    @staticmethod
    def fix_rarity(rarity: str) -> int:
        return {"S": 5, "A": 4, "B": 3}.get(rarity, 4)

    async def get_final_data(self, characters: List["ZZZPartialCharacter"], client: "ZZZClient") -> List[AvatarData]:
        details = await self.get_avatars_details(characters, client)
        data = []
        for character in characters:
            try:
                detail = details.get(character.id)
                equip = (
                    EquipmentData(
                        id=detail.weapon.id,
                        name=detail.weapon.name,
                        level=detail.weapon.level,
                        eidolon=detail.weapon.star,
                        rarity=self.fix_rarity(detail.weapon.rarity),
                        icon=self.assets_service.weapon.icon(detail.weapon.id, detail.weapon.name).as_uri(),
                    )
                    if detail.weapon
                    else None
                )
                avatar = AvatarData(
                    id=character.id,
                    name=character.name,
                    level=character.level,
                    eidolon=character.rank,
                    rarity=self.fix_rarity(character.rarity),
                    icon=self.assets_service.avatar.icon(character.id, character.name).as_uri(),
                    skills=self.get_skill_data(detail),
                    equipment=equip,
                )
                data.append(avatar)
            except AssetsCouldNotFound as e:
                logger.warning("未找到角色 %s[%s] 的资源: %s", character.name, character.id, e)
        return data

    async def avatar_list_render(
        self,
        base_render_data: Dict,
        avatar_datas: List[AvatarData],
        only_one_page: bool,
    ) -> Union[Tuple[Any], List["RenderResult"], None]:
        def render_task(start_id: int, c: List[AvatarData]):
            _render_data = {
                "avatar_datas": c,  # 角色数据
                "start_id": start_id,  # 开始序号
            }
            _render_data.update(base_render_data)
            return self.template_service.render(
                "zzz/avatar_list/main.html",
                _render_data,
                viewport={"width": 1040, "height": 500},
                full_page=True,
                query_selector=".container",
                file_type=FileType.PHOTO,
                ttl=30 * 24 * 60 * 60,
            )

        if only_one_page:
            return [await render_task(0, avatar_datas)]
        image_count = len(avatar_datas)
        while image_count > MAX_AVATAR_COUNT:
            image_count /= 2
        image_count = math.ceil(image_count)
        avatar_datas_group = [avatar_datas[i : i + image_count] for i in range(0, len(avatar_datas), image_count)]
        tasks = [render_task(i * image_count, c) for i, c in enumerate(avatar_datas_group)]
        return await asyncio.gather(*tasks)

    async def add_theme_data(self, data: Dict, player_id: int):
        res = RESOURCE_DIR / "img"
        data["avatar"] = (res / "avatar.png").as_uri()
        data["background"] = (res / "home.png").as_uri()
        return data

    async def render(self, client: "ZZZClient", all_avatars: bool = False) -> List["RenderResult"]:
        characters: List["ZZZPartialCharacter"] = await self.get_avatars_data(client)

        has_more = (not all_avatars) and len(characters) > MAX_AVATAR_COUNT
        if has_more:
            characters = characters[:MAX_AVATAR_COUNT]
        avatar_datas = await self.get_final_data(characters, client)

        base_render_data = {
            "uid": mask_number(client.player_id),  # 玩家uid
            "has_more": has_more,  # 是否显示了全部角色
        }
        await self.add_theme_data(base_render_data, client.player_id)
        return await self.avatar_list_render(base_render_data, avatar_datas, has_more)

    @handler.command("avatars", cookie=True, block=False)
    @handler.message(filters.Regex(r"^(全部)?练度统计$"), cookie=True, block=False)
    async def avatar_list(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE"):
        user_id = await self.get_real_user_id(update)
        message = update.effective_message
        uid, offset = self.get_real_uid_or_offset(update)
        all_avatars = "全部" in message.text or "all" in message.text  # 是否发送全部角色
        self.log_user(update, logger.info, "[bold]练度统计[/bold]: all=%s", all_avatars, extra={"markup": True})
        await message.reply_chat_action(ChatAction.TYPING)

        async with self.helper.genshin(user_id, player_id=uid, offset=offset) as client:
            notice = await message.reply_text("彦卿需要收集整理数据，还请耐心等待哦~")
            self.add_delete_message_job(notice, delay=60)
            images = await self.render(client, all_avatars)

        for group in ArkoWrapper(images).group(10):  # 每 10 张图片分一个组
            await RenderGroupResult(results=group).reply_media_group(message, write_timeout=60)

        self.log_user(
            update,
            logger.info,
            "[bold]练度统计[/bold]发送图片成功",
            extra={"markup": True},
        )

    async def avatar_list_use_by_inline(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        callback_query = update.callback_query
        user = update.effective_user
        user_id = user.id
        uid = IInlineUseData.get_uid_from_context(context)
        self.log_user(update, logger.info, "查询练度统计")

        async with self.helper.genshin(user_id, player_id=uid) as client:
            client: "ZZZClient"
            images = await self.render(client)
            render = images[0]
        await render.edit_inline_media(callback_query)

    async def get_inline_use_data(self) -> List[Optional[IInlineUseData]]:
        return [
            IInlineUseData(
                text="练度统计",
                hash="avatar_list",
                callback=self.avatar_list_use_by_inline,
                cookie=True,
                player=True,
            )
        ]
