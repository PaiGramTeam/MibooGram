import datetime
from asyncio import sleep
from typing import TYPE_CHECKING

from simnet.errors import (
    TimedOut as SimnetTimedOut,
    BadRequest as SimnetBadRequest,
    InvalidCookies,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden

from core.plugin import Plugin, job
from core.services.history_data.services import (
    HistoryDataAbyssServices,
    HistoryDataLedgerServices,
)
from gram_core.basemodel import RegionEnum
from gram_core.plugin import handler
from gram_core.services.cookies import CookiesService
from gram_core.services.cookies.models import CookiesStatusEnum
from plugins.zzz.challenge import ChallengePlugin
from plugins.tools.genshin import GenshinHelper, PlayerNotFoundError, CookiesNotFoundError
from utils.log import logger

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

    from simnet import ZZZClient

REGION = [RegionEnum.HYPERION, RegionEnum.HOYOLAB]
NOTICE_TEXT = """#### %s更新 ####
时间：%s (UTC+8)
UID: %s
结果: 新的%s已保存，可通过命令回顾"""


class RefreshHistoryJob(Plugin):
    """历史记录定时刷新"""

    def __init__(
        self,
        cookies: CookiesService,
        genshin_helper: GenshinHelper,
        history_abyss: HistoryDataAbyssServices,
        history_ledger: HistoryDataLedgerServices,
    ):
        self.cookies = cookies
        self.genshin_helper = genshin_helper
        self.history_data_abyss = history_abyss
        self.history_data_ledger = history_ledger

    @staticmethod
    async def send_notice(context: "ContextTypes.DEFAULT_TYPE", user_id: int, notice_text: str):
        try:
            await context.bot.send_message(user_id, notice_text, parse_mode=ParseMode.HTML)
        except (BadRequest, Forbidden) as exc:
            logger.error("执行自动刷新历史记录时发生错误 user_id[%s] Message[%s]", user_id, exc.message)
        except Exception as exc:
            logger.error("执行自动刷新历史记录时发生错误 user_id[%s]", user_id, exc_info=exc)

    async def save_abyss_data(self, client: "ZZZClient") -> bool:
        uid = client.player_id
        abyss_data = await client.get_zzz_challenge(uid, previous=False, lang="zh-cn")
        if abyss_data.has_data:
            return await ChallengePlugin.save_abyss_data(self.history_data_abyss, uid, abyss_data)
        return False

    async def send_abyss_notice(self, context: "ContextTypes.DEFAULT_TYPE", user_id: int, uid: int):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notice_text = NOTICE_TEXT % ("防卫战历史记录", now, uid, "挑战记录")
        await self.send_notice(context, user_id, notice_text)

    @handler.command(command="remove_same_history", block=False, admin=True)
    async def remove_same_history(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE"):
        user = update.effective_user
        logger.info("用户 %s[%s] remove_same_history 命令请求", user.full_name, user.id)
        message = update.effective_message
        reply = await message.reply_text("正在执行移除相同数据历史记录任务，请稍后...")
        text = "移除相同数据历史记录任务完成\n"
        num1 = await self.history_data_abyss.remove_same_data()
        text += f"防卫战数据移除数量：{num1}\n"
        await reply.edit_text(text)

    @handler.command(command="refresh_all_history", block=False, admin=True)
    async def refresh_all_history(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        user = update.effective_user
        logger.info("用户 %s[%s] refresh_all_history 命令请求", user.full_name, user.id)
        message = update.effective_message
        reply = await message.reply_text("正在执行刷新历史记录任务，请稍后...")
        await self.daily_refresh_history(context)
        await reply.edit_text("全部账号刷新历史记录任务完成")

    @job.run_daily(time=datetime.time(hour=6, minute=1, second=0), name="RefreshHistoryJob")
    async def daily_refresh_history(self, context: "ContextTypes.DEFAULT_TYPE"):
        logger.info("正在执行每日刷新历史记录任务")
        for database_region in REGION:
            for cookie_model in await self.cookies.get_all(
                region=database_region, status=CookiesStatusEnum.STATUS_SUCCESS
            ):
                user_id = cookie_model.user_id
                try:
                    async with self.genshin_helper.genshin(user_id) as client:
                        if await self.save_abyss_data(client):
                            await self.send_abyss_notice(context, user_id, client.player_id)
                except (InvalidCookies, PlayerNotFoundError, CookiesNotFoundError):
                    continue
                except SimnetBadRequest as exc:
                    logger.warning(
                        "用户 user_id[%s] 请求历史记录失败 [%s]%s", user_id, exc.ret_code, exc.original or exc.message
                    )
                    continue
                except SimnetTimedOut:
                    logger.info("用户 user_id[%s] 请求历史记录超时", user_id)
                    continue
                except Exception as exc:
                    logger.error("执行自动刷新历史记录时发生错误 user_id[%s]", user_id, exc_info=exc)
                    continue
                await sleep(1)

        logger.success("执行每日刷新历史记录任务完成")
