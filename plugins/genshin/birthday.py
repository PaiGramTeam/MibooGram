import re
from datetime import datetime

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from telegram.ext import filters

from core.baseplugin import BasePlugin
from core.plugin import Plugin, handler
from metadata.genshin import AVATAR_DATA
from metadata.shortname import roleToId, roleToName
from utils.bot import get_all_args
from utils.decorators.error import error_callable
from utils.decorators.restricts import restricts
from utils.log import logger


class BirthdayPlugin(Plugin, BasePlugin):
    """Birthday."""

    def __init__(self):
        """Load Data."""
        self.birthday_list = {}
        for value in AVATAR_DATA.values():
            key = "_".join([str(i) for i in value["birthday"]])
            data = self.birthday_list.get(key, [])
            data.append(value["name"])
            self.birthday_list.update({key: data})

    @handler(CommandHandler, command="birthday", block=False)
    @restricts()
    @error_callable
    async def command_start(self, update: Update, context: CallbackContext) -> None:
        message = update.effective_message
        user = update.effective_user
        key = datetime.now().strftime("%m_%d")
        args = get_all_args(context)
        if len(args) >= 1:
            msg = args[0]
            logger.info(f"用户 {user.full_name}[{user.id}] 查询角色生日命令请求 || 参数 {msg}")
            if re.match(r"\d{1,2}.\d{1,2}", msg):
                try:
                    key = re.findall(r"\d+", msg)[0] + "_" + re.findall(r"\d+", msg)[1]
                    day_list = self.birthday_list.get(key, [])
                    date = re.findall(r"\d+", msg)[0] + "月" + re.findall(r"\d+", msg)[1] + "日"
                    text = f"{date} 是 {'、'.join(day_list)} 的生日哦~" if day_list else f"{date} 没有角色过生日哦~"
                except IndexError:
                    text = "请输入正确的日期格式，如1-1，或输入正确的角色名称。"
                reply_message = await message.reply_text(text)
                if filters.ChatType.GROUPS.filter(reply_message):
                    self._add_delete_message_job(context, message.chat_id, message.message_id)
                    self._add_delete_message_job(context, reply_message.chat_id, reply_message.message_id)
            else:
                try:
                    name = roleToName(msg)
                    aid = str(roleToId(msg))
                    birthday = AVATAR_DATA[aid]["birthday"]
                    text = f"{name} 的生日是 {birthday[0]}月{birthday[1]}日 哦~"
                    reply_message = await message.reply_text(text)
                    if filters.ChatType.GROUPS.filter(reply_message):
                        self._add_delete_message_job(context, message.chat_id, message.message_id)
                        self._add_delete_message_job(context, reply_message.chat_id, reply_message.message_id)
                except KeyError:
                    reply_message = await message.reply_text(
                        "请输入正确的日期格式，如1-1，或输入正确的角色名称。"
                    )
                    if filters.ChatType.GROUPS.filter(reply_message):
                        self._add_delete_message_job(context, message.chat_id, message.message_id)
                        self._add_delete_message_job(context, reply_message.chat_id, reply_message.message_id)
        else:
            logger.info(f"用户 {user.full_name}[{user.id}] 查询今日角色生日列表")
            today_list = self.birthday_list.get(key, [])
            text = f"今天是 {'、'.join(today_list)} 的生日哦~" if today_list else "今天没有角色过生日哦~"
            reply_message = await message.reply_text(text)
            if filters.ChatType.GROUPS.filter(reply_message):
                self._add_delete_message_job(context, message.chat_id, message.message_id)
                self._add_delete_message_job(context, reply_message.chat_id, reply_message.message_id)