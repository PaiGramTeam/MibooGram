import math
from typing import TYPE_CHECKING, List, Tuple, Optional, Union

from simnet.models.zzz.calculator import ZZZCalculatorCharacterDetails, ZZZCalculatorAvatarProperty
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatAction
from telegram.ext import filters

from core.config import config
from core.dependence.redisdb import RedisDB
from core.plugin import Plugin, handler
from core.services.template.services import TemplateService
from metadata.shortname import roleToName, idToRole
from plugins.tools.genshin import GenshinHelper
from utils.log import logger
from utils.uid import mask_number

if TYPE_CHECKING:
    from simnet import ZZZClient
    from telegram import Update
    from telegram.ext import ContextTypes
    from core.services.template.models import RenderResult

__all__ = ("AgentDetailPlugin",)


class ZZZCalculatorAvatarPropertyModify(ZZZCalculatorAvatarProperty):

    @property
    def icon(self) -> str:
        return {
            "生命值": "hp",
            "攻击力": "atk",
            "防御力": "def",
            "冲击力": "impact",
            "暴击率": "crit-rate",
            "暴击伤害": "crit-dmg",
            "异常掌控": "anomaly-proficiency",
            "异常精通": "anomaly-mastery",
            "穿透率": "pen-ratio",
            "能量自动回复": "energy-regen",
        }.get(self.property_name, "")


color_map = {
    "1011": "#c8e16c",
    "1021": "#a0351c",
    "1031": "#e6adaa",
    "1041": "#febb2e",
    "1061": "#c8d7bd",
    "1081": "#af3e3a",
    "1101": "#de643d",
    "1111": "#ddc374",
    "1121": "#a68d73",
    "1131": "#28bdcc",
    "1141": "#d0d3e0",
    "1151": "#e8cda2",
    "1181": "#b75339",
    "1191": "#c9becc",
    "1211": "#c4c1b1",
    "1241": "#4e7ebd",
    "1281": "#e9d892",
}


class NeedClient(Exception):
    """无缓存，需要 StarRailClient"""


class AgentDetailPlugin(Plugin):
    """角色详细信息查询"""

    def __init__(
        self,
        helper: GenshinHelper,
        template_service: TemplateService,
        redis: RedisDB,
    ):
        self.template_service = template_service
        self.helper = helper
        self.qname = "plugins:agent_detail"
        self.redis = redis.client
        self.expire = 15 * 60  # 15分钟
        self.kitsune: Optional[str] = None

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

    def parse_render_data(self, data: "ZZZCalculatorCharacterDetails", nickname: str, ch_id: int, uid: int):
        char = None
        for i in data.characters:
            if i.id == ch_id:
                char = i
                break
        props = [ZZZCalculatorAvatarPropertyModify(**i.dict()) for i in char.properties]
        return {
            "uid": mask_number(uid),
            "char": char,
            "props": props,
            "color": color_map.get(str(char.id), "#010101"),
        }

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
                    callback_data=f"get_role_detail|{user_id}|{uid}|{idToRole(value.id)}",
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
                    callback_data=f"get_role_detail|{user_id}|{uid}|{last_page}",
                )
            )
        if last_page or next_page:
            last_button.append(
                InlineKeyboardButton(
                    f"{page}/{all_page}",
                    callback_data=f"get_role_detail|{user_id}|{uid}|empty_data",
                )
            )
        if next_page:
            last_button.append(
                InlineKeyboardButton(
                    "下一页 >>",
                    callback_data=f"get_role_detail|{user_id}|{uid}|{next_page}",
                )
            )
        if last_button:
            send_buttons.append(last_button)
        return send_buttons

    async def get_render_result(
        self, data: "ZZZCalculatorCharacterDetails", nickname: str, ch_id: int, uid: int
    ) -> "RenderResult":
        final = self.parse_render_data(data, nickname, ch_id, uid)
        return await self.template_service.render(
            "zzz/agent_detail/agent_detail.html",
            final,
            {"width": 1024, "height": 1200},
            query_selector=".shareContainer_2ZR-xeyd",
            full_page=True,
        )

    @staticmethod
    def get_caption(data: "ZZZCalculatorCharacterDetails", character_id: int) -> str:
        tags = []
        for character in data.characters:
            if character.id == character_id:
                tags.append(character.name)
                tags.append(f"等级{character.level}")
                tags.append(f"命座{character.rank}")
                if weapon := character.weapon:
                    tags.append(weapon.name)
                    tags.append(f"武器等级{weapon.level}")
                    tags.append(f"精{weapon.star}")
                break
        return "#" + " #".join(tags)

    @handler.command(command="agent_detail", block=False)
    @handler.message(filters=filters.Regex("^角色详细信息查询(.*)"), block=False)
    async def command_start(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
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
            "角色详细信息查询命令请求 || character_name[%s]",
            ch_name,
        )
        await message.reply_chat_action(ChatAction.TYPING)
        async with self.helper.genshin(user_id, player_id=uid, offset=offset) as client:
            nickname, data = await self.get_characters(client.player_id, client)
        uid = client.player_id
        if ch_name is None:
            buttons = self.gen_button(data, user_id, uid)
            if isinstance(self.kitsune, str):
                photo = self.kitsune
            else:
                photo = open("resources/img/aaa.jpg", "rb")
            await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
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
        render_result = await self.get_render_result(data, nickname, characters.id, client.player_id)
        await render_result.reply_photo(
            message,
            filename=f"{client.player_id}.png",
            reply_markup=self.get_custom_button(user_id, uid, characters.id),
            caption=self.get_caption(data, characters.id),
        )

    @handler.callback_query(pattern=r"^get_role_detail\|", block=False)
    async def get_role_detail(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> None:
        callback_query = update.callback_query
        user = callback_query.from_user
        message = callback_query.message

        async def get_role_detail_callback(
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

        result, user_id, uid = await get_role_detail_callback(callback_query.data)
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
                "用户 %s[%s] 角色详细信息查询命令请求 || page[%s] uid[%s]",
                user.full_name,
                user.id,
                page,
                uid,
            )
        else:
            logger.info(
                "用户 %s[%s] 角色详细信息查询命令请求 || character_name[%s] uid[%s]",
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
        render_result = await self.get_render_result(data, nickname, characters.id, uid)
        render_result.filename = f"role_detail_{uid}_{result}.png"
        render_result.caption = self.get_caption(data, characters.id)
        await render_result.edit_media(message, reply_markup=self.get_custom_button(user.id, uid, characters.id))

    @staticmethod
    def get_custom_button(user_id: int, uid: int, char_id: int) -> Optional[InlineKeyboardMarkup]:
        return None
