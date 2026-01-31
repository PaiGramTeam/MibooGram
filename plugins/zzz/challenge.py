"""防卫战数据查询"""

import math
from functools import lru_cache
from typing import List, Optional, Tuple

from simnet.models.zzz.chronicle.challenge import ZZZChallenge
from telegram import Message, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import CallbackContext, filters, ContextTypes

from core.dependence.assets import AssetsService
from core.plugin import Plugin, handler
from core.services.history_data.models import HistoryDataAbyss
from core.services.history_data.services import HistoryDataAbyssServices
from core.services.template.models import RenderResult
from core.services.template.services import TemplateService
from gram_core.config import config
from gram_core.dependence.redisdb import RedisDB
from plugins.tools.genshin import GenshinHelper
from utils.enkanetwork import RedisCache
from utils.log import logger
from utils.uid import mask_number

try:
    import ujson as jsonlib

except ImportError:
    import json as jsonlib


MAX_FLOOR = 7
MAX_STARS = MAX_FLOOR * 3


@lru_cache
def get_args(text: str) -> bool:
    prev = "pre" in text or "上期" in text
    return prev


class AbyssUnlocked(Exception):
    """根本没动"""


class AbyssFastPassed(Exception):
    """快速通过，无数据"""


class ChallengePlugin(Plugin):
    """防卫战数据查询"""

    def __init__(
        self,
        template: TemplateService,
        helper: GenshinHelper,
        assets_service: AssetsService,
        history_data_abyss: HistoryDataAbyssServices,
        redis: RedisDB,
    ):
        self.template_service = template
        self.helper = helper
        self.assets_service = assets_service
        self.history_data_abyss = history_data_abyss
        self.cache = RedisCache(redis.client, key="plugin:challenge:history")

    async def get_uid(self, user_id: int, reply: Optional[Message], player_id: int, offset: int) -> int:
        """通过消息获取 uid，优先级：args > reply > self"""
        uid, user_id_ = player_id, user_id
        if reply:
            try:
                user_id_ = reply.from_user.id
            except AttributeError:
                pass
        if not uid:
            player_info = await self.helper.players_service.get_player(user_id_, offset=offset)
            if player_info is not None:
                uid = player_info.player_id
            if (not uid) and (user_id_ != user_id):
                player_info = await self.helper.players_service.get_player(user_id, offset=offset)
                if player_info is not None:
                    uid = player_info.player_id
        return uid

    def get_floor_data(self, abyss_data: "ZZZChallenge", floor: int):
        try:
            floor_data = abyss_data.floors[-floor]
        except IndexError:
            floor_data = None
        if not floor_data:
            raise AbyssUnlocked()

        character_icons = {
            ch.id: self.assets_service.avatar.square(ch.id).as_uri()
            for ch in floor_data.node_1.avatars + floor_data.node_2.avatars
        }
        buddy_icons = {
            bu.id: self.assets_service.buddy.icon(bu.id).as_uri()
            for bu in [floor_data.node_1.buddy, floor_data.node_2.buddy]
            if bu
        }

        render_data = {
            "floor": floor_data,
            "floor_time": floor_data.floor_challenge_time.datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "floor_nodes": [floor_data.node_1, floor_data.node_2],
            "floor_num": floor,
            "character_icons": character_icons,
            "buddy_icons": buddy_icons,
        }
        return render_data

    @staticmethod
    def from_seconds_to_hours(seconds: int) -> str:
        hours = seconds / 3600
        minutes = (seconds % 3600) / 60
        sec = seconds % 60
        return f"{int(hours)}时{int(minutes)}分{int(sec)}秒"

    async def get_rendered_pic(  # skipcq: PY-R1000 #
        self,
        abyss_data: "ZZZChallenge",
        uid: int,
    ) -> RenderResult:
        """
        获取渲染后的图片

        Args:
            abyss_data (ZZZChallenge): 防卫战数据
            uid (int): 需要查询的 uid

        Returns:
            bytes格式的图片
        """

        if not abyss_data.has_data:
            raise AbyssUnlocked()
        start_time = abyss_data.begin_time.datetime.strftime("%m月%d日 %H:%M")
        end_time = abyss_data.end_time.datetime.strftime("%m月%d日 %H:%M")
        dura = self.from_seconds_to_hours(abyss_data.fast_layer_time)
        max_floor_map = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七"}
        max_floor = f"第{max_floor_map.get(abyss_data.max_layer, abyss_data.max_layer)}防线"

        render_data = {
            "title": "防卫战",
            "start_time": start_time,
            "end_time": end_time,
            "stars": abyss_data.rating_list,
            "uid": mask_number(uid),
            "max_floor": max_floor,
            "max_dura": dura,
            "floor_colors": {
                1: "#374952",
                2: "#374952",
                3: "#55464B",
                4: "#55464B",
                5: "#55464B",
                6: "#1D2A5D",
                7: "#1D2A5D",
                8: "#1D2A5D",
                9: "#292B58",
                10: "#382024",
                11: "#252550",
                12: "#1D2A4A",
            },
        }

        floors_data = []
        floors = abyss_data.floors[::-1]
        for i in range(len(floors)):
            try:
                floors_data.append(self.get_floor_data(abyss_data, i + 1))
            except AbyssFastPassed:
                pass
        render_data["floors"] = floors_data

        return await self.template_service.render(
            "zzz/abyss/overview.html",
            render_data,
            viewport={"width": 1893, "height": 4000},
            query_selector=".container",
        )

    @staticmethod
    async def save_abyss_data(
        history_data_abyss: "HistoryDataAbyssServices", uid: int, abyss_data: "ZZZChallenge"
    ) -> bool:
        model = history_data_abyss.create(uid, abyss_data)
        old_data = await history_data_abyss.get_by_user_id_data_id(uid, model.data_id)
        exists = history_data_abyss.exists_data(model, old_data)
        if not exists:
            await history_data_abyss.add(model)
            return True
        return False

    async def get_abyss_data(self, uid: int):
        return await self.history_data_abyss.get_by_user_id(uid)

    @staticmethod
    def get_season_data_name(data: "HistoryDataAbyss"):
        last_battles = data.abyss_data.floors[0]
        start_time = last_battles.floor_challenge_time.datetime
        time = start_time.strftime("%Y.%m.%d")
        name = ""
        if "第" in last_battles.zone_name:
            name = last_battles.zone_name.split("第")[0]
        honor = ""
        if data.abyss_data.total_stars == MAX_STARS:
            honor = "👑"
            num_of_characters = max(
                len(last_battles.node_1.avatars),
                len(last_battles.node_2.avatars),
            )
            if num_of_characters == 2:
                honor = "双通"
            elif num_of_characters == 1:
                honor = "单通"

        return f"{name} {time} {data.abyss_data.total_stars} ★ {honor}".strip()

    async def get_session_button_data(self, user_id: int, uid: int, force: bool = False):
        redis = await self.cache.get(str(uid))
        if redis and not force:
            return redis["buttons"]
        data = await self.get_abyss_data(uid)
        data.sort(key=lambda x: x.id, reverse=True)
        abyss_data = [HistoryDataAbyss.from_data(i) for i in data]
        buttons = [
            {
                "name": self.get_season_data_name(abyss_data[idx]),
                "value": f"get_abyss_history|{user_id}|{uid}|{value.id}",
            }
            for idx, value in enumerate(data)
        ]
        await self.cache.set(str(uid), {"buttons": buttons})
        return buttons

    async def gen_season_button(
        self,
        user_id: int,
        uid: int,
        page: int = 1,
    ) -> List[List[InlineKeyboardButton]]:
        """生成按钮"""
        data = await self.get_session_button_data(user_id, uid)
        if not data:
            return []
        buttons = [
            InlineKeyboardButton(
                value["name"],
                callback_data=value["value"],
            )
            for value in data
        ]
        all_buttons = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        send_buttons = all_buttons[(page - 1) * 7 : page * 7]
        last_page = page - 1 if page > 1 else 0
        all_page = math.ceil(len(all_buttons) / 7)
        next_page = page + 1 if page < all_page and all_page > 1 else 0
        last_button = []
        if last_page:
            last_button.append(
                InlineKeyboardButton(
                    "<< 上一页",
                    callback_data=f"get_abyss_history|{user_id}|{uid}|p_{last_page}",
                )
            )
        if last_page or next_page:
            last_button.append(
                InlineKeyboardButton(
                    f"{page}/{all_page}",
                    callback_data=f"get_abyss_history|{user_id}|{uid}|empty_data",
                )
            )
        if next_page:
            last_button.append(
                InlineKeyboardButton(
                    "下一页 >>",
                    callback_data=f"get_abyss_history|{user_id}|{uid}|p_{next_page}",
                )
            )
        if last_button:
            send_buttons.append(last_button)
        return send_buttons

    @handler.command("challenge_history_v1", block=False)
    @handler.message(filters.Regex(r"^旧版防卫战历史数据"), block=False)
    async def abyss_history_command_start(self, update: Update, _: CallbackContext) -> None:
        user_id = await self.get_real_user_id(update)
        message = update.effective_message
        uid, offset = self.get_real_uid_or_offset(update)
        uid: int = await self.get_uid(user_id, message.reply_to_message, uid, offset)
        self.log_user(update, logger.info, "查询防卫战 v1 历史数据 uid[%s]", uid)

        async with self.helper.genshin_or_public(user_id, uid=uid) as _:
            await self.get_session_button_data(user_id, uid, force=True)
            buttons = await self.gen_season_button(user_id, uid)
            if not buttons:
                await message.reply_text("还没有防卫战历史数据哦~")
                return
        await message.reply_text("请选择要查询的防卫战历史数据", reply_markup=InlineKeyboardMarkup(buttons))

    async def get_abyss_history_page(self, update: "Update", user_id: int, uid: int, result: str):
        """翻页处理"""
        callback_query = update.callback_query

        self.log_user(update, logger.info, "切换防卫战历史数据页 page[%s]", result)
        page = int(result.split("_")[1])
        async with self.helper.genshin_or_public(user_id) as _:
            buttons = await self.gen_season_button(user_id, uid, page)
            if not buttons:
                await callback_query.answer("还没有防卫战历史数据哦~", show_alert=True)
                await callback_query.edit_message_text("还没有防卫战历史数据哦~")
                return
        await callback_query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
        await callback_query.answer(f"已切换到第 {page} 页", show_alert=False)

    async def get_abyss_history_floor(self, update: "Update", data_id: int):
        """渲染层数数据"""
        callback_query = update.callback_query
        message = callback_query.message
        reply = None
        if message.reply_to_message:
            reply = message.reply_to_message

        data = await self.history_data_abyss.get_by_id(data_id)
        if not data:
            await callback_query.answer("数据不存在，请尝试重新发送命令", show_alert=True)
            await callback_query.edit_message_text("数据不存在，请尝试重新发送命令~")
            return
        abyss_data = HistoryDataAbyss.from_data(data)

        await callback_query.answer("正在渲染图片中 请稍等 请不要重复点击按钮", show_alert=False)

        images = await self.get_rendered_pic(abyss_data.abyss_data, data.user_id)

        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)

        await images.reply_photo(reply or message)
        self.log_user(update, logger.info, "[bold]防卫战挑战数据[/bold]: 成功发送图片", extra={"markup": True})
        self.add_delete_message_job(message, delay=1)

    @handler.callback_query(pattern=r"^get_abyss_history\|", block=False)
    async def get_abyss_history(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> None:
        callback_query = update.callback_query
        user = callback_query.from_user

        async def get_abyss_history_callback(
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

        result, user_id, uid = await get_abyss_history_callback(callback_query.data)
        if user.id != user_id:
            await callback_query.answer(text="这不是你的按钮！\n" + config.notice.user_mismatch, show_alert=True)
            return
        if result == "empty_data":
            await callback_query.answer(text="此按钮不可用", show_alert=True)
            return
        if result.startswith("p_"):
            await self.get_abyss_history_page(update, user_id, uid, result)
            return
        data_id = int(result)
        await self.get_abyss_history_floor(update, data_id)
