import math
from typing import List, Tuple, Union, Optional, TYPE_CHECKING, Dict

from pydantic import BaseModel
from simnet import ZZZClient
from simnet.models.zzz.calculator import (
    ZZZCalculatorCharacterDetails,
    ZZZCalculatorCharacter,
    ZZZCalculatorCharacterEquipPlanInfo,
    ZZZCalculatorEquipment,
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import filters

from core.config import config
from core.dependence.assets import AssetsService
from core.dependence.redisdb import RedisDB
from core.plugin import Plugin, handler
from core.services.players import PlayersService
from core.services.template.services import TemplateService
from core.services.wiki.services import WikiService
from metadata.shortname import roleToName, idToRole
from plugins.tools.genshin import GenshinHelper
from plugins.tools.player_detail import PlayerDetailHelper, NeedClient
from utils.log import logger
from utils.uid import mask_number

if TYPE_CHECKING:
    from telegram.ext import ContextTypes
    from telegram import Update

try:
    import ujson as jsonlib
except ImportError:
    import json as jsonlib


class PlayerCards(Plugin):
    def __init__(
        self,
        helper: GenshinHelper,
        player_service: PlayersService,
        template_service: TemplateService,
        assets_service: AssetsService,
        wiki_service: WikiService,
        redis: RedisDB,
    ):
        self.helper = helper
        self.player_service = player_service
        self.assets_service = assets_service
        self.template_service = template_service
        self.wiki_service = wiki_service
        self.kitsune: Optional[str] = None
        self.fight_prop_rule: Dict[str, Dict[str, float]] = {}
        self.player_detail_helper = PlayerDetailHelper(helper, redis)

    async def get_characters(
        self, uid: int, client: "ZZZClient" = None
    ) -> Tuple[Optional[str], Optional["ZZZCalculatorCharacterDetails"]]:
        return await self.player_detail_helper.get_characters(uid, client)

    @staticmethod
    def get_caption(character: "ZZZCalculatorCharacter") -> str:
        tags = []
        tags.append(character.name)
        tags.append(f"等级{character.level}")
        tags.append(f"命座{character.rank}")
        if weapon := character.weapon:
            tags.append(weapon.name)
            tags.append(f"武器等级{weapon.level}")
            tags.append(f"精{weapon.star}")
        return "#" + " #".join(tags)

    @handler.command(command="player_card", player=True, block=False)
    @handler.command(command="agent_detail", player=True, block=False)
    @handler.message(filters=filters.Regex("^角色卡片查询(.*)"), player=True, block=False)
    async def player_cards(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        user_id = await self.get_real_user_id(update)
        message = update.effective_message
        uid, offset = self.get_real_uid_or_offset(update)
        args = self.get_args(context)
        ch_name = None
        for i in args:
            if i.startswith("@"):
                continue
            ch_name = roleToName(i)
            if ch_name:
                break
        self.log_user(
            update,
            logger.info,
            "角色卡片信息查询命令请求 || character_name[%s]",
            ch_name,
        )
        await message.reply_chat_action(ChatAction.TYPING)
        async with self.helper.genshin(user_id, player_id=uid, offset=offset) as client:
            nickname, data = await self.get_characters(client.player_id, client)
        uid = client.player_id
        if ch_name is not None:
            self.log_user(
                update,
                logger.info,
                "角色卡片查询命令请求 || character_name[%s] uid[%s]",
                ch_name,
                uid,
            )
        else:
            self.log_user(update, logger.info, "角色卡片查询命令请求")

            buttons = self.gen_button(data, user_id, uid)
            if isinstance(self.kitsune, str):
                photo = self.kitsune
            else:
                photo = open("resources/img/aaa.jpg", "rb")
            reply_message = await message.reply_photo(
                photo=photo,
                caption=f"请选择你要查询的角色 - UID {uid}",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            if reply_message.photo:
                self.kitsune = reply_message.photo[-1].file_id
            return
        for characters in data.characters:
            if idToRole(characters.id) == ch_name:
                break
        else:
            await message.reply_text(f"未在游戏中找到 {ch_name} ，请检查角色是否存在，或者等待角色数据更新后重试")
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        render_result = await RenderTemplate(
            uid,
            characters,
            self.template_service,
            self.assets_service,
            self.wiki_service,
            self.fight_prop_rule,
        ).render()  # pylint: disable=W0631
        await render_result.reply_photo(
            message,
            filename=f"player_card_{uid}_{ch_name}.png",
            caption=self.get_caption(characters),
        )

    @handler.callback_query(pattern=r"^get_player_card\|", block=False)
    async def get_player_cards(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> None:
        callback_query = update.callback_query
        user = callback_query.from_user
        message = callback_query.message

        async def get_player_card_callback(
            callback_query_data: str,
        ) -> Tuple[str, int, int]:
            _data = callback_query_data.split("|")
            _user_id = int(_data[1])
            _uid = int(_data[2])
            _result = _data[3]
            logger.debug(
                "callback_query_data函数返回 result[%s] user_id[%s] uid[%s]",
                _result,
                _user_id,
                _uid,
            )
            return _result, _user_id, _uid

        result, user_id, uid = await get_player_card_callback(callback_query.data)
        if user.id != user_id:
            await callback_query.answer(text="这不是你的按钮！\n" + config.notice.user_mismatch, show_alert=True)
            return
        if result == "empty_data":
            await callback_query.answer(text="此按钮不可用", show_alert=True)
            return
        page = 0
        if result.isdigit():
            page = int(result)
            logger.info(
                "用户 %s[%s] 角色卡片查询命令请求 || page[%s] uid[%s]",
                user.full_name,
                user.id,
                page,
                uid,
            )
        else:
            logger.info(
                "用户 %s[%s] 角色卡片查询命令请求 || character_name[%s] uid[%s]",
                user.full_name,
                user.id,
                result,
                uid,
            )
        try:
            nickname, data = await self.get_characters(uid)
        except NeedClient:
            async with self.helper.genshin(user.id, player_id=uid) as client:
                nickname, data = await self.get_characters(client.player_id, client)
        if page:
            buttons = self.gen_button(data, user.id, uid, page)
            await message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer(f"已切换到第 {page} 页", show_alert=False)
            return
        for characters in data.characters:
            if idToRole(characters.id) == result:
                break
        else:
            await message.delete()
            await callback_query.answer(
                f"未在游戏中找到 {result} ，请检查角色是否存在，或者等待角色数据更新后重试",
                show_alert=True,
            )
            return
        await callback_query.answer(text="正在渲染图片中 请稍等 请不要重复点击按钮", show_alert=False)
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        render_result = await RenderTemplate(
            uid,
            characters,
            self.template_service,
            self.assets_service,
            self.wiki_service,
            self.fight_prop_rule,
        ).render()  # pylint: disable=W0631
        render_result.filename = f"player_card_{uid}_{result}.png"
        render_result.caption = self.get_caption(characters)
        await render_result.edit_media(message)

    @staticmethod
    def gen_button(
        data: "ZZZCalculatorCharacterDetails",
        user_id: Union[str, int],
        uid: int,
        page: int = 1,
    ) -> List[List[InlineKeyboardButton]]:
        """生成按钮"""
        buttons = []

        if data.characters:
            buttons = [
                InlineKeyboardButton(
                    idToRole(value.id),
                    callback_data=f"get_player_card|{user_id}|{uid}|{idToRole(value.id)}",
                )
                for value in data.characters
                if value.id
            ]
        all_buttons = [buttons[i : i + 4] for i in range(0, len(buttons), 4)]
        send_buttons = all_buttons[(page - 1) * 3 : page * 3]
        last_page = page - 1 if page > 1 else 0
        all_page = math.ceil(len(all_buttons) / 3)
        next_page = page + 1 if page < all_page and all_page > 1 else 0
        last_button = []
        if last_page:
            last_button.append(
                InlineKeyboardButton(
                    "<< 上一页",
                    callback_data=f"get_player_card|{user_id}|{uid}|{last_page}",
                )
            )
        if last_page or next_page:
            last_button.append(
                InlineKeyboardButton(
                    f"{page}/{all_page}",
                    callback_data=f"get_player_card|{user_id}|{uid}|empty_data",
                )
            )
        if next_page:
            last_button.append(
                InlineKeyboardButton(
                    "下一页 >>",
                    callback_data=f"get_player_card|{user_id}|{uid}|{next_page}",
                )
            )
        if last_button:
            send_buttons.append(last_button)
        return send_buttons


class Artifact(BaseModel, frozen=False):
    """在 ZZZCalculatorEquipment 基础上扩展了遗器评分数据"""

    equipment: ZZZCalculatorEquipment
    # 遗器评分
    score: float = 0
    # 遗器评级
    score_label: str = "E"
    # 遗器评级颜色
    score_class: str = ""
    # 是否为有效词条
    valid_properties: List[bool] = []

    @staticmethod
    def get_score_class(label: str) -> str:
        mapping = {
            "F": "text-neutral-400",
            "D": "text-neutral-200",
            "C": "text-violet-400",
            "B": "text-violet-400",
            "A": "text-yellow-400",
            "S": "text-yellow-400",
            "SS": "text-yellow-400",
            "SSS": "text-red-500",
            "WTF": "text-red-500",
        }
        return mapping.get(label.replace("+", ""), "text-neutral-400")


class RenderTemplate:
    def __init__(
        self,
        uid: Union[int, str],
        character: "ZZZCalculatorCharacter",
        template_service: TemplateService,
        assets_service: AssetsService,
        wiki_service: WikiService,
        fight_prop_rule: Dict[str, Dict[str, float]],
    ):
        self.uid = uid
        self.template_service = template_service
        self.character = character
        self.assets_service = assets_service
        self.wiki_service = wiki_service
        self.fight_prop_rule = fight_prop_rule

    async def render(self):
        images = await self.cache_images()

        equip_plan_info = self.character.equip_plan_info
        artifacts, valid_total = self.find_artifacts(equip_plan_info)
        artifact_total_score: float = sum(artifact.score for artifact in artifacts)
        artifact_total_score = round(artifact_total_score, 1)
        artifact_total_score_label: str = (equip_plan_info.equip_rating if equip_plan_info else None) or "E"
        artifact_total_score_class: str = Artifact.get_score_class(artifact_total_score_label)
        # 评分规则: 1=官方规则 3=用户自定义规则
        score_rule_type = equip_plan_info.type if equip_plan_info else None
        # 全部有效词条名称列表
        valid_property_names = (
            [prop.name for prop in equip_plan_info.plan_effective_property_list] if equip_plan_info else []
        )

        skills_map = [0, 2, 5, 1, 3, 4]
        data = {
            "uid": mask_number(self.uid),
            "character": self.character,
            "character_detail": self.wiki_service.character.get_by_id(self.character.id),
            "weapon": self.character.weapon if self.character.weapon and self.character.weapon.id else None,
            "weapon_detail": (
                self.wiki_service.weapon.get_by_id(self.character.weapon.id)
                if self.character.weapon and self.character.weapon.id
                else None
            ),
            # 遗器评分
            "artifact_total_score": artifact_total_score,
            # 遗器评级
            "artifact_total_score_label": artifact_total_score_label,
            # 遗器评级颜色
            "artifact_total_score_class": artifact_total_score_class,
            # 有效词条数
            "valid_property_cnt": valid_total,
            # 全部有效词条名称
            "valid_property_names": valid_property_names,
            # 评分规则类型: 1=官方 3=自定义
            "score_rule_type": score_rule_type,
            "artifacts": artifacts,
            "skills": [self.character.skills[skills_map[index]].level for index in range(6)],
            "images": images,
        }

        return await self.template_service.render(
            "zzz/player_card/player_card.html",
            data,
            {"width": 1000, "height": 1200},
            full_page=True,
            query_selector=".text-neutral-200",
            ttl=7 * 24 * 60 * 60,
        )

    async def cache_images(self):
        c = self.character
        cid = c.id
        data = {
            "banner_url": self.assets_service.avatar.gacha(cid).as_uri(),
            "skills": ["", "", "", "", "", ""],
            "constellations": ["", "", "", "", "", ""],
            "equipment": "",
        }
        if c.weapon and c.weapon.id:
            data["equipment"] = self.assets_service.weapon.icon(c.weapon.id).as_uri()
        return data

    def find_artifacts(
        self, equip_plan_info: Optional[ZZZCalculatorCharacterEquipPlanInfo]
    ) -> Tuple[List["Artifact"], int]:
        """根据 equip_plan_info 构造带评分的遗器列表，并统计有效词条数"""
        if not equip_plan_info:
            artifacts = [
                Artifact(
                    equipment=equip,
                    valid_properties=[False] * len(equip.properties),
                )
                for equip in self.character.equip
            ]
            return artifacts, 0
        effective_property_ids = {prop.id for prop in equip_plan_info.plan_effective_property_list}
        valid_total = equip_plan_info.valid_property_cnt
        artifacts: List["Artifact"] = []
        score_per_artifact = self._split_score(equip_plan_info.equip_rating_score, len(self.character.equip))
        for index, equip in enumerate(self.character.equip):
            valid_props = [
                equip.properties[i].property_id in effective_property_ids for i in range(len(equip.properties))
            ]
            artifact = Artifact(
                equipment=equip,
                score=round(score_per_artifact[index], 1) if index < len(score_per_artifact) else 0,
                score_label=equip_plan_info.equip_rating or "E",
                score_class=Artifact.get_score_class(equip_plan_info.equip_rating or "E"),
                valid_properties=valid_props,
            )
            artifacts.append(artifact)
        return artifacts, valid_total

    @staticmethod
    def _split_score(total_score: float, count: int) -> List[float]:
        """将总评分平均分配到每个遗器上"""
        if count <= 0:
            return []
        base = total_score / count
        return [base] * count
