import random
from typing import Optional, TYPE_CHECKING, List
from telegram.constants import ChatAction
from telegram.ext import filters

from core.config import config
from core.plugin import Plugin, handler
from core.services.cookies.error import TooManyRequestPublicCookies
from core.services.template.models import RenderResult
from core.services.template.services import TemplateService
from gram_core.plugin.methods.inline_use_data import IInlineUseData
from plugins.tools.genshin import GenshinHelper
from utils.const import RESOURCE_DIR
from utils.log import logger
from utils.uid import mask_number

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes
    from simnet import ZZZClient

__all__ = ("PlayerStatsPlugins",)


class PlayerStatsPlugins(Plugin):
    """玩家统计查询"""

    def __init__(self, template: TemplateService, helper: GenshinHelper):
        self.template_service = template
        self.helper = helper

    @handler.command("stats", player=True, block=False)
    @handler.message(filters.Regex("^玩家统计查询(.*)"), player=True, block=False)
    async def command_start(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> Optional[int]:
        user_id = await self.get_real_user_id(update)
        nickname = self.get_real_user_name(update)
        uid, offset = self.get_real_uid_or_offset(update)
        message = update.effective_message
        self.log_user(update, logger.info, "查询游戏用户命令请求")
        try:
            async with self.helper.genshin_or_public(user_id, uid=uid, offset=offset) as client:
                if not client.public:
                    await client.get_record_cards()
                render_result = await self.render(client, nickname)
        except TooManyRequestPublicCookies:
            await message.reply_text("用户查询次数过多 请稍后重试")
            return
        except AttributeError as exc:
            logger.error("角色数据有误")
            logger.exception(exc)
            await message.reply_text(f"角色数据有误 估计是{config.notice.bot_name}晕了")
            return
        except ValueError as exc:
            logger.warning("获取 uid 发生错误！ 错误信息为 %s", str(exc))
            await message.reply_text("输入错误")
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await render_result.reply_photo(message, filename=f"{client.player_id}.png")

    async def render(self, client: "ZZZClient", nickname: str) -> RenderResult:
        uid = client.player_id
        user_info = await client.get_zzz_user(uid)

        data = {
            "uid": mask_number(uid),
            "stats": user_info.stats,
            "nickname": nickname,
            "stats_labels": [
                ("活跃天数", "active_days"),
                ("获取角色数", "avatar_num"),
                ("绳网声望", "world_level_name"),
                ("式舆防卫战防线", "cur_period_zone_layer_count"),
                ("获得邦布数", "buddy_num"),
            ],
            "style": "main",  # nosec
        }
        await self.add_theme_data(data, uid)
        return await self.template_service.render(
            "zzz/stats/stats.html",
            data,
            {"width": 650, "height": 400},
            full_page=True,
        )

    async def stats_use_by_inline(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        callback_query = update.callback_query
        user = update.effective_user
        nickname = self.get_real_user_name(update)
        user_id = user.id
        uid = IInlineUseData.get_uid_from_context(context)

        self.log_user(update, logger.info, "查询游戏用户命令请求")
        notice = None
        try:
            async with self.helper.genshin_or_public(user_id, uid=uid) as client:
                if not client.public:
                    await client.get_record_cards()
                render_result = await self.render(client, nickname)
        except TooManyRequestPublicCookies:
            notice = "用户查询次数过多 请稍后重试"
        except AttributeError as exc:
            logger.error("角色数据有误")
            logger.exception(exc)
            notice = f"角色数据有误 估计是{config.notice.bot_name}晕了"
        except ValueError as exc:
            logger.warning("获取 uid 发生错误！ 错误信息为 %s", str(exc))
            notice = "UID 内部错误"

        if notice:
            await callback_query.answer(notice, show_alert=True)
            return
        await render_result.edit_inline_media(callback_query)

    async def add_theme_data(self, data, player_id: int):
        res = RESOURCE_DIR / "img"
        data["avatar"] = (res / "avatar.png").as_uri()
        data["background"] = (res / "home.png").as_uri()
        return data

    async def get_inline_use_data(self) -> List[Optional[IInlineUseData]]:
        return [
            IInlineUseData(
                text="玩家统计",
                hash="stats",
                callback=self.stats_use_by_inline,
                player=True,
            ),
        ]
