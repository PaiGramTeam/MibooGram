from datetime import datetime, timedelta
from typing import Optional

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import CallbackContext, filters

from core.dependence.redisdb import RedisDB
from core.plugin import Plugin, handler
from modules.apihelper.client.components.calendar import Calendar
from utils.log import logger


class CalendarPlugin(Plugin):
    """活动日历查询"""

    def __init__(
        self,
        redis: RedisDB,
    ):
        self.calendar = Calendar()
        self.cache = redis.client

    async def _fetch_data(self) -> Optional[str]:
        if data := await self.cache.get("plugin:calendar"):
            return data.decode("utf-8")
        data = await self.calendar.get_calendar_url()
        if not data:
            return None
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        await self.cache.set("plugin:calendar", data, ex=next_hour - now)
        return data

    @handler.command("calendar", block=False)
    @handler.message(filters=filters.Regex(r"^(活动)+(日历|日历列表)$"), block=False)
    async def command_start(self, update: Update, _: CallbackContext) -> None:
        message = update.effective_message
        mode = "list" if "列表" in message.text else "calendar"
        self.log_user(update, logger.info, "查询日历 | 模式 %s", mode)
        await message.reply_chat_action(ChatAction.TYPING)
        data = await self._fetch_data()
        if not data:
            reply = await message.reply_text("查询失败，请稍后再试")
            if filters.ChatType.GROUPS.filter(message):
                self.add_delete_message_job(reply)
                self.add_delete_message_job(message)
            return
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        await message.reply_photo(data)
