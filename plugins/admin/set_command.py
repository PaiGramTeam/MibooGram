from typing import TYPE_CHECKING

from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from core.plugin import Plugin, handler
from core.config import config
from utils.log import logger

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


class SetCommandPlugin(Plugin):
    @handler.command("set_command", block=False, admin=True)
    @handler.command("set_commands", block=False, admin=True)
    async def set_command(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] 发出 set_command 命令", user.full_name, user.id)
        user_command = [
            BotCommand("cancel", "取消操作（解决一切玄学问题）"),
            BotCommand("help_raw", "查看文本帮助"),
            # gacha_log 相关
            BotCommand("signal_log", "查看调频记录"),
            BotCommand("signal_log_import", "导入调频记录"),
            BotCommand("signal_log_export", "导出调频记录"),
            BotCommand("signal_log_delete", "删除调频记录"),
            # Cookie 查询类
            BotCommand("sign", "米游社绝区零每日签到"),
            BotCommand("dailynote_tasks", "自动便笺提醒"),
            # 其他
            BotCommand("setuid", "添加/重设UID"),
            BotCommand("setcookie", "添加/重设Cookie"),
            BotCommand("player", "管理用户绑定玩家"),
            BotCommand("verify", "手动验证"),
        ]
        group_command = [
            # 通用
            BotCommand("help", "帮助"),
            # Wiki 类
            BotCommand("weapon", "查看音擎图鉴"),
            BotCommand("avatar", "查询角色攻略"),
            # UID 查询类
            BotCommand("stats", "玩家统计查询"),
            # Cookie 查询类
            BotCommand("dailynote", "查询实时便笺"),
            BotCommand("cookies_import", "从其他 BOT 导入账号信息"),
            BotCommand("cookies_export", "导出账号信息给其他 BOT"),
        ]
        admin_command = [
            BotCommand("add_admin", "添加管理员"),
            BotCommand("del_admin", "删除管理员"),
            BotCommand("save_entry", "保存条目数据"),
            BotCommand("remove_all_entry", "删除全部条目数据"),
            BotCommand("sign_all", "全部账号重新签到"),
            BotCommand("send_log", "发送日志"),
            BotCommand("update", "更新"),
            BotCommand("set_command", "重设命令"),
            BotCommand("status", "当前Bot运行状态"),
            BotCommand("leave_chat", "退出群组"),
            BotCommand("get_chat", "获取会话信息"),
            BotCommand("add_block", "添加黑名单"),
            BotCommand("del_block", "移除黑名单"),
        ]
        await context.bot.set_my_commands(
            commands=group_command
        )  # 留空，default 为 botCommandScopeDefault, 所有聊天可见
        await context.bot.set_my_commands(commands=user_command + group_command, scope=BotCommandScopeAllPrivateChats())
        if config.error.notification_chat_id:
            await context.bot.set_my_commands(
                commands=admin_command + group_command + user_command,
                scope=BotCommandScopeChat(config.error.notification_chat_id),
            )
        await message.reply_text("设置命令成功")
