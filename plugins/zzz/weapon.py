from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import CallbackContext, filters

from core.plugin import Plugin, handler
from core.services.game.services import GameCacheService
from core.services.search.models import StrategyEntry
from core.services.search.services import SearchServices
from core.services.wiki.services import WikiService
from metadata.shortname import weaponToTag, weaponToName
from utils.log import logger


class WeaponPlugin(Plugin):
    """音擎图鉴查询"""

    KEYBOARD = [
        [InlineKeyboardButton(text="查看音擎列表并查询", switch_inline_query_current_chat="查看音擎列表并查询")]
    ]

    def __init__(
        self,
        cache_service: GameCacheService = None,
        wiki_service: WikiService = None,
        search_service: SearchServices = None,
    ):
        self.cache_service = cache_service
        self.wiki_service = wiki_service
        self.search_service = search_service

    @handler.command(command="weapon", block=False)
    @handler.message(filters=filters.Regex("^音擎图鉴查询(.*)"), block=False)
    async def command_start(self, update: Update, context: CallbackContext) -> None:
        message = update.effective_message
        args = self.get_args(context)
        if len(args) >= 1:
            weapon_name = args[0]
        else:
            reply_message = await message.reply_text(
                "请回复你要查询的音擎名称", reply_markup=InlineKeyboardMarkup(self.KEYBOARD)
            )
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        weapon_name = weaponToName(weapon_name)
        file_path = self.wiki_service.raider.raider_light_cone_path / f"{weapon_name}.png"
        if not file_path.exists():
            reply_message = await message.reply_text(
                f"没有找到 {weapon_name} 的图鉴", reply_markup=InlineKeyboardMarkup(self.KEYBOARD)
            )
            if filters.ChatType.GROUPS.filter(reply_message):
                self.add_delete_message_job(message)
                self.add_delete_message_job(reply_message)
            return
        self.log_user(update, logger.info, "查询音擎图鉴命令请求 || 参数 %s", weapon_name)
        await message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
        caption = "From 米游社@听语惊花"
        if file_id := await self.cache_service.get_weapon_cache(weapon_name):
            await message.reply_photo(
                photo=file_id,
                caption=caption,
                filename=f"{weapon_name}.png",
                parse_mode=ParseMode.HTML,
            )
        else:
            reply_photo = await message.reply_photo(
                photo=open(file_path, "rb"),
                caption=caption,
                filename=f"{weapon_name}.png",
                parse_mode=ParseMode.HTML,
            )
            if reply_photo.photo:
                tags = weaponToTag(weapon_name)
                photo_file_id = reply_photo.photo[0].file_id
                await self.cache_service.set_weapon_cache(weapon_name, photo_file_id)
                entry = StrategyEntry(
                    key=f"plugin:strategy:{weapon_name}",
                    title=weapon_name,
                    description=f"{weapon_name} 音擎图鉴",
                    tags=tags,
                    caption=caption,
                    parse_mode="HTML",
                    photo_file_id=photo_file_id,
                )
                await self.search_service.add_entry(entry)
