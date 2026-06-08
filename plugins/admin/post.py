import asyncio
import math
import os
import re
from asyncio import create_subprocess_shell, subprocess
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional, Tuple, TYPE_CHECKING

import aiofiles
from arkowrapper import ArkoWrapper
from bs4 import BeautifulSoup
from httpx import Timeout
from pyrogram.errors import FloodWait, BadRequest as PyroBadRequest
from pyrogram.file_id import FileId
from pyrogram.raw.functions.messages import SendMessage
from pyrogram.raw.types import InputDocument, InputPhoto, InputRichMessage
from pyrogram.types import InputMediaPhoto, InputMediaVideo
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.constants import MessageLimit, ParseMode
from telegram.error import BadRequest
from telegram.ext import ConversationHandler, filters

from core.config import config
from core.plugin import Plugin, conversation, handler
from gram_core.basemodel import Settings, SettingsConfigDict
from gram_core.dependence.mtproto import MTProto
from gram_core.dependence.redisdb import RedisDB
from gram_core.plugin import job
from gram_core.services.groups.services import GroupService
from metadata.post_tags import POST_TAGS
from modules.apihelper.client.components.hoyolab import Hoyolab
from modules.apihelper.client.components.hyperion import Hyperion, HyperionBase
from modules.apihelper.error import APIHelperException
from modules.apihelper.models.genshin.hyperion import ArtworkImage, PostTypeEnum
from modules.errorpush import SentryClient
from utils.helpers import sha1
from utils.log import logger
from utils.rich_text import PhotoType, json_to_blocks, BlockList

if TYPE_CHECKING:
    from pyrogram import Client

    from telegram import Update, Message
    from telegram.ext import ContextTypes

    from modules.apihelper.models.genshin.hyperion import PostRecommend, PostInfo


class PostHandlerData:
    def __init__(self):
        self.channel_id: int = -1
        self.url: str = ""
        self.tags: Optional[List[str]] = []
        self.rich: Optional[InputRichMessage] = None
        # 旧版推送相关字段
        self.post_text: str = ""
        self.post_text_caption: str = ""
        self.post_images: Optional[List["ArtworkImage"]] = None
        self.delete_photo: Optional[List[int]] = []
        self.old_channel_id: int = -1


class PostConfig(Settings):
    """文章推送配置"""

    chat_id: Optional[int] = 0
    chat_ids: List[int] = []
    auto: Optional[bool] = False
    new_channels: List[int] = []

    model_config = SettingsConfigDict(env_prefix="post_")


@dataclass
class FetchedPostData:
    """``fetch_post_data`` 的返回值聚合，避免元组解包过深。"""

    post_info: "PostInfo"
    rich: "InputRichMessage"
    post_tags: List[str]
    url: str
    post_subject: str
    post_images: List["ArtworkImage"]
    post_text: str
    post_text_caption: str


CHECK_POST, SEND_POST, CHECK_COMMAND, GTE_DELETE_PHOTO = range(10900, 10904)
GET_POST_CHANNEL, GET_TAGS, GET_TEXT, GET_VIDEO = range(10904, 10908)
# 旧版推送对话状态
CHECK_POST_OLD, CHECK_COMMAND_OLD = range(10908, 10910)
GET_POST_CHANNEL_OLD, SEND_POST_OLD = range(10910, 10912)
post_config = PostConfig()


class Post(Plugin.Conversation):
    """文章推送"""

    MENU_KEYBOARD = ReplyKeyboardMarkup([["推送频道", "添加TAG"], ["退出"]], True, True)
    # 旧版推送的菜单：与旧版 post.py 保持基本一致
    MENU_OLD_KEYBOARD = ReplyKeyboardMarkup([["推送频道", "添加TAG"], ["退出"]], True, True)

    def __init__(self, redis: RedisDB, group_service: GroupService, mtp: MTProto):
        self.gids = [8]
        self.ffmpeg_enable = False
        self.cache_dir = os.path.join(os.getcwd(), "cache")
        self.cache = redis.client
        self.cache_key = "plugin:post:pushed"
        self.group_service = group_service
        self.send_lock = asyncio.Lock()  # 添加锁对象，确保 send_post_images 函数无法并发执行
        self.mtp = mtp
        assert mtp.client is not None, "必须启用 pyrogram 支持"

    def get_cache_key(self, bbs_type: "PostTypeEnum") -> str:
        return f"{self.cache_key}:{bbs_type.value}"

    async def is_posted(self, bbs_type: "PostTypeEnum", post_id: int) -> bool:
        key = self.get_cache_key(bbs_type)
        return await self.cache.sismember(key, post_id)

    async def set_posted(self, bbs_type: "PostTypeEnum", post_id: int) -> bool:
        key = self.get_cache_key(bbs_type)
        return await self.cache.sadd(key, post_id)

    async def is_posted_empty(self, bbs_type: "PostTypeEnum") -> bool:
        key = self.get_cache_key(bbs_type)
        return await self.cache.scard(key) == 0

    @staticmethod
    def get_bbs_client(bbs_type: "PostTypeEnum") -> "HyperionBase":
        class_type = Hyperion if bbs_type == PostTypeEnum.CN else Hoyolab
        return class_type(
            timeout=Timeout(
                connect=config.connect_timeout,
                read=config.read_timeout,
                write=config.write_timeout,
                pool=config.pool_timeout,
            )
        )

    async def initialize(self):
        if config.channels and len(config.channels) > 0:
            logger.success("文章定时推送处理已经开启")
        output, _ = await self.execute("ffmpeg -version")
        if "ffmpeg version" in output:
            self.ffmpeg_enable = True
            logger.info("检测到 ffmpeg 可用 已经启动编码转换")
            logger.debug("ffmpeg version info\n%s", output)
        else:
            logger.warning("ffmpeg 不可用 已经禁用编码转换")

    @job.run_cron(cron="*/2 6-20 * * *", name="post_task.busy")
    @job.run_cron(cron="*/30 21-23,0-5 * * *", name="post_task.idle")
    @SentryClient.monitor(monitor_slug="PostTaskJob")
    async def task_all(self, context: "ContextTypes.DEFAULT_TYPE"):
        if not config.channels or len(config.channels) <= 0:
            return
        tasks = [self.task(context, PostTypeEnum.CN), self.task(context, PostTypeEnum.OS)]
        await asyncio.gather(*tasks)

    async def task(self, context: "ContextTypes.DEFAULT_TYPE", post_type: "PostTypeEnum"):
        bbs = self.get_bbs_client(post_type)

        # 请求推荐POST列表并处理
        official_recommended_posts = []
        try:
            for gid in self.gids:
                official_recommended_posts.extend(await bbs.get_official_recommended_posts(gid))
            await bbs.close()
        except APIHelperException as exc:
            logger.error("获取首页推荐信息失败 %s", str(exc))
            return

        # 判断是否为空
        if not official_recommended_posts:
            return
        if await self.is_posted_empty(post_type):
            for post in official_recommended_posts:
                await self.set_posted(post_type, post.post_id)
            return

        # 筛选出新推送的文章
        new_post_id_list = [
            post for post in official_recommended_posts if not await self.is_posted(post_type, post.post_id)
        ]
        if not new_post_id_list:
            return

        await self.task_send_message(context, new_post_id_list, post_type)

    async def task_send_message(
        self, context: "ContextTypes.DEFAULT_TYPE", new_post_id_list: list["PostRecommend"], post_type: "PostTypeEnum"
    ):
        chat_ids = post_config.chat_ids or post_config.chat_id or config.owner
        if not isinstance(chat_ids, list):
            chat_ids = [chat_ids]

        for post in new_post_id_list:
            post_id, gids = post.post_id, post.gids
            type_name = post.type_enum.value
            buttons = [
                [
                    InlineKeyboardButton("确认", callback_data=f"post_admin|confirm|{type_name}|{post_id}"),
                    InlineKeyboardButton("取消", callback_data=f"post_admin|cancel|{type_name}|{post_id}"),
                ]
            ]
            url = post.get_fix_url()
            tag = f"#{post.short_name} #{post_type.value} #{post.short_name}_{post_type.value}"
            text = f"发现官网推荐文章 <a href='{url}'>{post.subject}</a>\n是否开始处理 {tag}"

            # 1. 发送通知给管理员（手动推送选项）
            for chat_id in chat_ids:
                try:
                    await context.bot.send_message(
                        chat_id,
                        text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(buttons),
                    )
                except BadRequest as exc:
                    logger.error("发送消息失败 %s", exc.message)

            if post_type is PostTypeEnum.CN and post_config.auto:
                # 2. 自动推送逻辑
                logger.info("检测到新文章，准备执行自动推送 post_id[%s] post_type[%s]", post_id, post_type)
                auto_push_success = await self.auto_send_post(post_id, post_type)

                # 3. 标记为已推送
                await self.set_posted(post_type, post_id)
                if not auto_push_success:
                    logger.warning("自动推送失败，但仍标记为已推送 post_id[%s]", post_id)
                    # 发送错误通知给管理员
                    error_text = f"自动推送失败\n文章ID: {post_id}\n文章类型: {post_type.value}\n文章标题: {post.subject}\n请检查日志获取详细错误信息 #error"
                    for chat_id in chat_ids:
                        try:
                            await context.bot.send_message(chat_id, error_text)
                            logger.info("已向管理员发送自动推送失败通知 post_id[%s]", post_id)
                        except BadRequest as exc:
                            logger.error("发送自动推送失败通知失败 %s", exc.message)
            else:
                await self.set_posted(post_type, post_id)

    @staticmethod
    async def execute(command: str) -> Tuple[str, int]:
        process = await create_subprocess_shell(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        try:
            result = str(stdout.decode().strip()) + str(stderr.decode().strip())
        except UnicodeDecodeError:
            result = str(stdout.decode("gbk").strip()) + str(stderr.decode("gbk").strip())
        return result, process.returncode

    @staticmethod
    def get_ffmpeg_command(input_file: str, output_file: str):
        return (
            f'ffmpeg -i "{input_file}" '
            f'-c:v libx264 -crf 20 -vf "fps=30,format=yuv420p,'
            f'scale=trunc(iw/2)*2:trunc(ih/2)*2" -y "{output_file}"'
        )

    async def gif_to_mp4(self, media: "List[ArtworkImage]"):
        if self.ffmpeg_enable:
            for i in media:
                if i.file_extension == "gif":
                    file_path = os.path.join(self.cache_dir, i.file_name)
                    file_name, _ = os.path.splitext(i.file_name)
                    output_file = file_name + ".mp4"
                    output_path = os.path.join(self.cache_dir, output_file)
                    if os.path.exists(output_path):
                        async with aiofiles.open(output_path, mode="rb") as f:
                            i.data = await f.read()
                        i.file_name = output_file
                        i.file_extension = "mp4"
                        continue
                    async with aiofiles.open(file_path, mode="wb") as f:
                        await f.write(i.data)
                    temp_file = sha1(file_name) + ".mp4"
                    temp_path = os.path.join(self.cache_dir, temp_file)
                    command = self.get_ffmpeg_command(file_path, temp_path)
                    result, return_code = await self.execute(command)
                    if return_code == 0:
                        if os.path.exists(temp_path):
                            logger.debug("ffmpeg 执行成功\n%s", result)
                            os.rename(temp_path, output_path)
                            async with aiofiles.open(output_path, mode="rb") as f:
                                i.data = await f.read()
                                i.file_name = output_file
                                i.file_extension = "mp4"
                        else:
                            logger.error(
                                "输出文件不存在！可能是 ffmpeg 命令执行失败！\n"
                                "file_path[%s]\noutput_path[%s]\ntemp_file[%s]\nffmpeg result[%s]",
                                file_path,
                                output_path,
                                temp_path,
                                result,
                            )
                    else:
                        logger.error("ffmpeg 执行失败\n%s", result)
        return media

    @staticmethod
    def parse_post_text(soup: BeautifulSoup, post_subject: str) -> Tuple[str, bool]:
        """解析旧版推送用的纯文本 caption，pyrogram 不需要 MarkdownV2 转义。"""

        def parse_tag(_tag) -> str:
            if _tag.name == "a":
                href = _tag.get("href")
                if href and href.startswith("/"):
                    href = f"https://www.miyoushe.com{href}"
                if href and href.startswith("http"):
                    return f"[{_tag.get_text()}]({href})"
            return _tag.get_text()

        post_text = f"{post_subject}\n\n"
        start = True
        too_long = False
        if post_p := soup.find_all("p"):
            try:
                for p in post_p:
                    t = p.get_text()
                    if not t and start:
                        continue
                    start = False
                    for tag in p.contents:
                        post_text_ = post_text + parse_tag(tag)
                        if len(post_text_) >= (MessageLimit.CAPTION_LENGTH - 55):
                            raise RecursionError
                        post_text = post_text_
                    post_text += "\n"
            except RecursionError:
                too_long = True
        else:
            post_text += f"{soup.get_text()}\n"
        post_text = re.sub(r"\n{3,}", "\n\n", post_text).strip()
        return post_text, too_long

    @staticmethod
    def safe_cut(text: str, length: int) -> str:
        """按字符长度截断。"""
        return text[:length]

    @conversation.entry_point
    @handler.callback_query(pattern=r"^post_admin\|", block=False)
    async def callback_query_start(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        post_handler_data = context.chat_data.get("post_handler_data")
        if post_handler_data is None:
            post_handler_data = PostHandlerData()
            context.chat_data["post_handler_data"] = post_handler_data
        callback_query = update.callback_query
        user = callback_query.from_user
        message = callback_query.message
        logger.info("用户 %s[%s] POST命令请求", user.full_name, user.id)

        async def get_post_admin_callback(callback_query_data: str) -> Tuple[str, PostTypeEnum, int]:
            _data = callback_query_data.split("|")
            _result = _data[1]
            _post_type = PostTypeEnum(_data[2])
            _post_id = int(_data[3])
            logger.debug(
                "callback_query_data函数返回 result[%s] _post_type[%s] post_id[%s]", _result, _post_type, _post_id
            )
            return _result, _post_type, _post_id

        result, post_type, post_id = await get_post_admin_callback(callback_query.data)

        if result == "cancel":
            await message.reply_text("操作已经取消")
            await message.delete()
        elif result == "confirm":
            reply_text = await message.reply_text("正在处理")
            status = await self.send_post_info(post_handler_data, message, post_id, post_type)
            await reply_text.delete()
            return status

        return ConversationHandler.END

    @conversation.entry_point
    @handler.command(command="post", block=False, admin=True)
    async def command_start(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] POST命令请求", user.full_name, user.id)
        post_handler_data = context.chat_data.get("post_handler_data")
        if post_handler_data is None:
            post_handler_data = PostHandlerData()
            context.chat_data["post_handler_data"] = post_handler_data
        text = f"✿✿ヽ（°▽°）ノ✿ 你好！ {user.username} ，\n" "只需复制URL回复即可 \n" "退出投稿只需回复退出"
        reply_keyboard = [["退出"]]
        await message.reply_text(text, reply_markup=ReplyKeyboardMarkup(reply_keyboard, True, True))
        return CHECK_POST

    @conversation.state(state=CHECK_POST)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def check_post(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        post_handler_data: PostHandlerData = context.chat_data.get("post_handler_data")
        message = update.effective_message
        if message.text == "退出":
            await message.reply_text("退出投稿", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END

        post_id, post_type = Hyperion.extract_post_id(update.message.text)
        if post_id == -1:
            await message.reply_text("获取作品ID错误，请检查连接是否合法", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        return await self.send_post_info(post_handler_data, message, post_id, post_type)

    @conversation.entry_point
    @handler.command(command="post_old", block=False, admin=True)
    async def command_start_old(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        """旧版推送入口，复用 pyrogram.send_media_group 发送 MarkdownV2 文本。"""
        user = update.effective_user
        message = update.effective_message
        logger.info("用户 %s[%s] POST_OLD命令请求", user.full_name, user.id)
        post_handler_data = context.chat_data.get("post_handler_data")
        if post_handler_data is None:
            post_handler_data = PostHandlerData()
            context.chat_data["post_handler_data"] = post_handler_data
        text = (
            f"✿✿ヽ（°▽°）ノ✿ 你好！ {user.username} ，\n"
            "旧版推送流程启动，只需复制URL回复即可 \n"
            "退出投稿只需回复退出"
        )
        reply_keyboard = [["退出"]]
        await message.reply_text(text, reply_markup=ReplyKeyboardMarkup(reply_keyboard, True, True))
        return CHECK_POST_OLD

    @conversation.state(state=CHECK_POST_OLD)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def check_post_old(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        post_handler_data: PostHandlerData = context.chat_data.get("post_handler_data")
        message = update.effective_message
        if message.text == "退出":
            await message.reply_text("退出投稿", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END

        post_id, post_type = Hyperion.extract_post_id(update.message.text)
        if post_id == -1:
            await message.reply_text("获取作品ID错误，请检查连接是否合法", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        return await self.send_post_info_old(post_handler_data, message, post_id, post_type)

    @staticmethod
    def get_tags_by_subject(post_subject: str) -> List[str]:
        """根据文章标题预设规则设置标签"""
        tags = []
        for tag, patterns in POST_TAGS.items():
            for pattern in patterns:
                if re.search(pattern, post_subject):
                    tags.append(tag)
                    break
        return tags

    async def get_file_id(self, i: ArtworkImage) -> str | None:
        max_retries = 5
        bot: "Client" = self.mtp.client
        for attempt in range(max_retries):
            try:
                if i.is_gif:
                    file = await bot.send_animation(config.channels_helper, BytesIO(i.data), file_name=i.file_name)
                    file_id = file.animation.file_id
                elif i.is_video:
                    file = await bot.send_video(config.channels_helper, BytesIO(i.data), file_name=i.file_name)
                    file_id = file.video.file_id
                else:
                    file = await bot.send_photo(config.channels_helper, BytesIO(i.data))
                    file_id = file.photo.file_id
                return file_id
            except FloodWait as exc:
                wait_seconds = int(exc.value) + 1
                logger.warning(
                    "post 插件 get_file_id 触发 FloodWait, 等待 %s 秒后重试 (第 %s/%s 次)",
                    wait_seconds,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(wait_seconds)
        logger.warning("post 插件 get_file_id 达到最大重试次数仍然失败 url[%s]", i.url)
        return None

    async def prepare_photos(self, photos: list[PhotoType], post_images: list[ArtworkImage]):
        new_photos, input_photos, input_documents = [], [], []
        photos_map = {i.src: i for i in photos}
        url_map: dict[str, list[ArtworkImage]] = OrderedDict()
        for i in post_images:
            url_map.setdefault(i.url, []).append(i)
            file_id = await self.get_file_id(i)
            if file_id:
                i.file_id = file_id
        for k, v in url_map.items():
            photo = photos_map.get(k)
            if not photo:
                continue
            for t in v:
                file_id = t.file_id
                if not file_id:
                    continue
                file = FileId.decode(file_id)
                if not file:
                    continue
                new_photo = PhotoType(
                    id=file.media_id,
                    src=photo.src,
                    block=photo.block,
                    is_gif=t.is_gif,
                    is_video=t.is_video,
                )
                new_photos.append(new_photo)
                if t.is_gif or t.is_video:
                    d = InputDocument(
                        id=file.media_id, access_hash=file.access_hash, file_reference=file.file_reference
                    )
                    input_documents.append(d)
                else:
                    p = InputPhoto(id=file.media_id, access_hash=file.access_hash, file_reference=file.file_reference)
                    input_photos.append(p)
        return new_photos, input_photos, input_documents

    async def fetch_post_data(self, post_id: int, post_type: "PostTypeEnum") -> "FetchedPostData":
        """获取文章数据的核心函数，可被自动推送和手动推送共用"""
        bbs = self.get_bbs_client(post_type)
        post_info = await bbs.get_post_info(self.gids[0], post_id)
        post_images = await bbs.get_images_by_post_id(self.gids[0], post_id)
        await bbs.close()
        post_images = await self.gif_to_mp4(post_images)
        post_data = post_info["post"]["post"]
        post_subject = post_data["subject"]
        post_subject_re = post_subject + post_info.user_nickname
        post_tags = self.get_tags_by_subject(post_subject_re)
        url = post_info.get_url()

        blocks, photos = json_to_blocks(post_info.structured_content)
        async with self.send_lock:  # 使用锁确保函数无法并发执行
            new_photos, input_photos, input_documents = await self.prepare_photos(photos, post_images)
        blocks.add_title(post_subject)
        blocks.fix_photo_block(new_photos)
        blocks.ignore_invalid_photo_block()
        blocks.merge_adjacent_photo_blocks()

        rich = InputRichMessage(blocks=blocks, photos=input_photos or None, documents=input_documents or None)

        # 旧版推送需要使用 BeautifulSoup 解析的纯文本 caption
        post_soup = BeautifulSoup(post_info.content, features="html.parser")
        post_text, too_long = self.parse_post_text(post_soup, post_subject)
        max_len = MessageLimit.CAPTION_LENGTH - 100
        if too_long or len(post_text) >= max_len:
            post_text = self.safe_cut(post_text, max_len)
        post_text += f"\n\n[source]({url})"
        post_text_caption = post_text + "".join([f" #{tag}" for tag in post_tags])

        return FetchedPostData(
            post_info=post_info,
            rich=rich,
            post_tags=post_tags,
            url=url,
            post_subject=post_subject_re,
            post_images=post_images,
            post_text=post_text,
            post_text_caption=post_text_caption,
        )

    async def send_post_info(
        self, post_handler_data: PostHandlerData, message: "Message", post_id: int, post_type: "PostTypeEnum"
    ) -> int:
        """新版手动推送流程，使用 InputRichMessage"""
        data = await self.fetch_post_data(post_id, post_type)
        if data.post_info.video_urls:
            await message.reply_text("检测到视频，需要单独下载，视频链接：" + "\n".join(data.post_info.video_urls))
        try:
            await self.send_post_images(
                message.chat_id,
                message.message_id,
                data.rich,
            )
        except PyroBadRequest as exc:
            await message.reply_text(f"发送图片时发生错误 {exc.value}", reply_markup=ReplyKeyboardRemove())
            logger.error("Post模块发送图片时发生错误 %s", exc.value)
            return ConversationHandler.END
        except TypeError as exc:
            await message.reply_text("发送图片时发生错误，错误信息已经写到日记", reply_markup=ReplyKeyboardRemove())
            logger.error("Post模块发送图片时发生错误", exc_info=exc)
            return ConversationHandler.END
        post_handler_data.url = data.url
        post_handler_data.tags = data.post_tags
        post_handler_data.channel_id = -1
        post_handler_data.rich = data.rich
        # 旧版字段也准备好，方便用户后续切到旧版推送
        post_handler_data.post_text = data.post_text
        post_handler_data.post_text_caption = data.post_text_caption
        post_handler_data.post_images = data.post_images
        post_handler_data.delete_photo = []
        await message.reply_text("请选择你的操作", reply_markup=self.MENU_KEYBOARD)
        return CHECK_COMMAND

    async def send_post_info_old(
        self, post_handler_data: PostHandlerData, message: "Message", post_id: int, post_type: "PostTypeEnum"
    ) -> int:
        """旧版手动推送流程，使用 send_media_group + MarkdownV2 文本"""
        data = await self.fetch_post_data(post_id, post_type)
        if data.post_info.video_urls:
            await message.reply_text("检测到视频，需要单独下载，视频链接：" + "\n".join(data.post_info.video_urls))
        try:
            await self.send_post_old_images(
                message.chat_id,
                message.message_id,
                data.post_images,
                data.post_text_caption,
            )
        except PyroBadRequest as exc:
            await message.reply_text(f"发送图片时发生错误 {exc.value}", reply_markup=ReplyKeyboardRemove())
            logger.error("Post模块（旧版）发送图片时发生错误 %s", exc.value)
            return ConversationHandler.END
        except TypeError as exc:
            await message.reply_text("发送图片时发生错误，错误信息已经写到日记", reply_markup=ReplyKeyboardRemove())
            logger.error("Post模块（旧版）发送图片时发生错误", exc_info=exc)
            return ConversationHandler.END
        post_handler_data.url = data.url
        post_handler_data.tags = data.post_tags
        post_handler_data.post_text = data.post_text
        post_handler_data.post_text_caption = data.post_text_caption
        post_handler_data.post_images = data.post_images
        post_handler_data.delete_photo = []
        post_handler_data.old_channel_id = -1
        await message.reply_text("请选择你的操作", reply_markup=self.MENU_OLD_KEYBOARD)
        return CHECK_COMMAND_OLD

    async def send_post_images(
        self,
        chat_id: int,
        reply_id: Optional[int],
        rich,
    ):
        bot = self.mtp.client
        peer = await bot.resolve_peer(chat_id)
        await bot.invoke(
            SendMessage(
                peer=peer,
                message="",
                random_id=bot.rnd_id(),
                rich_message=rich,
            )
        )

    @staticmethod
    def _build_pyrogram_media(post_images: List["ArtworkImage"]):
        """根据 ArtworkImage 的 file_id 构造 pyrogram 的 InputMedia 列表。

        ``prepare_photos`` 阶段已经将每张图片上传到辅助频道并把 ``file_id`` 写回
        ``ArtworkImage.file_id``，因此这里直接使用 ``file_id`` 即可，规避重复上传。
        """
        media = []
        for img in post_images:
            if img.is_error:
                continue
            if img.is_gif or img.is_video:
                media.append(InputMediaVideo(media=img.file_id, file_name=img.file_name))
            else:
                media.append(InputMediaPhoto(media=img.file_id))
        return media

    async def send_post_old_images(
        self,
        chat_id: int,
        reply_id: Optional[int],
        post_images: List["ArtworkImage"],
        post_text_caption: str,
    ):
        """旧版推送：使用 pyrogram.send_media_group + 纯文本 caption。

        多于 10 张时按 10 张一组发送，caption 放在最后一组第一项。
        """
        bot: "Client" = self.mtp.client
        async with self.send_lock:  # 与新版共享同一把锁，避免同一时间重复上传
            media = self._build_pyrogram_media(post_images)
            if not media:
                # 没有可用图片，直接发送纯文本
                await bot.send_message(chat_id, post_text_caption[: MessageLimit.TEXT_LENGTH])
                return
            if len(media) > 1:
                index = (math.ceil(len(media) / 10) - 1) * 10
                media[index].caption = post_text_caption
                for group in ArkoWrapper(media).group(10):
                    await bot.send_media_group(
                        chat_id,
                        list(group),
                        reply_to_message_id=reply_id,
                    )
            else:
                image = post_images[0]
                caption = post_text_caption[: MessageLimit.CAPTION_LENGTH]
                if image.is_video:
                    await bot.send_video(chat_id, image.file_id, caption=caption, reply_to_message_id=reply_id)
                elif image.is_gif:
                    await bot.send_animation(chat_id, image.file_id, caption=caption, reply_to_message_id=reply_id)
                else:
                    await bot.send_photo(chat_id, image.file_id, caption=caption, reply_to_message_id=reply_id)

    @staticmethod
    def get_channel_id_by_post_text(post_text: str) -> tuple[int, int]:
        index = 0
        if not config.channels:
            return 0, index
        if "千星奇域" in post_text and len(config.channels) > 1:
            index = 1
        channel_id = config.channels[index]
        return channel_id, index

    async def get_chat_username(self, chat_id: int) -> str:
        group = await self.group_service.get_group_by_id(chat_id)
        if group and group.username:
            return group.username
        try:
            chat = await self.application.bot.get_chat(chat_id)
        except Exception as exc:
            logger.error("获取频道信息失败 %s", str(exc))
            return ""
        return chat.username

    async def auto_send_post(self, post_id: int, post_type: "PostTypeEnum") -> bool:
        """自动推送流程：先 get_file_id，再同时发送新版 rich 与旧版 media_group。

        新版频道 ID 通过 ``post_config.new_channels`` 控制；若该列表为空则跳过
        新版推送。旧版频道 ID 来自 ``config.channels``，与旧版插件行为一致。
        """
        try:
            # 1. 获取文章数据（已包含 file_id 上传、rich、旧版文本等）
            data = await self.fetch_post_data(post_id, post_type)

            # 2. 自动选择旧版频道
            old_channel_id, old_channel_index = self.get_channel_id_by_post_text(data.post_subject)
            old_channel_name = await self.get_chat_username(old_channel_id)

            # 3. 准备旧版推送文本（拼接频道与 tag）
            old_caption = data.post_text_caption
            if old_channel_name:
                old_caption += f" @{old_channel_name}"
            for tag in data.post_tags:
                old_caption += f" #{tag}"

            # 4. 旧版推送（必须执行）
            await self.send_post_old_images(old_channel_id, None, data.post_images, old_caption)

            # 5. 新版推送（仅在 new_channels 中存在时执行）
            new_channel_ids = post_config.new_channels or []
            if len(new_channel_ids) > old_channel_index:
                new_channel_id = new_channel_ids[old_channel_index]
                new_channel_name = await self.get_chat_username(new_channel_id)
                data.rich.blocks.add_source_and_tags(data.url, new_channel_name, data.post_tags)
                try:
                    await self.send_post_images(new_channel_id, None, data.rich)
                    logger.info("自动推送新版文章成功 post_id[%s] channel[%s]", post_id, new_channel_id)
                except (PyroBadRequest, TypeError) as exc:
                    logger.error(
                        "自动推送新版文章失败 post_id[%s] channel[%s] %s",
                        post_id,
                        new_channel_id,
                        getattr(exc, "value", exc),
                    )
            logger.info("自动推送文章成功 post_id[%s]", post_id)
            return True
        except PyroBadRequest as exc:
            logger.error("自动推送时发送图片发生错误 %s", exc.value)
            return False
        except Exception as exc:
            logger.error("自动推送文章时发生错误", exc_info=exc)
            return False

    @conversation.state(state=CHECK_COMMAND)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def check_command(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        message = update.effective_message
        if message.text == "退出":
            await message.reply_text("退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        if message.text == "推送频道":
            return await self.get_channel(update, context)
        if message.text == "添加TAG":
            return await self.add_tags(update, context)
        return ConversationHandler.END

    async def get_channel(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> int:
        message = update.effective_message
        reply_keyboard = []
        try:
            for channel_id in config.channels:
                username = await self.get_chat_username(chat_id=channel_id)
                reply_keyboard.append([f"{username}"])
        except KeyError as error:
            logger.error("从配置文件获取频道信息发生错误，退出任务", exc_info=error)
            await message.reply_text("从配置文件获取频道信息发生错误，退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        await message.reply_text("请选择你要推送的频道", reply_markup=ReplyKeyboardMarkup(reply_keyboard, True, True))
        return GET_POST_CHANNEL

    @conversation.state(state=GET_POST_CHANNEL)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def get_post_channel(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        post_handler_data: PostHandlerData = context.chat_data.get("post_handler_data")
        message = update.effective_message
        channel_id = -1
        try:
            for channel_chat_id in config.channels:
                username = await self.get_chat_username(chat_id=channel_chat_id)
                if message.text == username:
                    channel_id = channel_chat_id
        except KeyError as exc:
            logger.error("从配置文件获取频道信息发生错误，退出任务", exc_info=exc)
            logger.exception(exc)
            await message.reply_text("从配置文件获取频道信息发生错误，退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        if channel_id == -1:
            await message.reply_text("获取频道信息失败，请检查你输入的内容是否正确", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        post_handler_data.channel_id = channel_id
        reply_keyboard = [["确认", "退出"]]
        await message.reply_text("请核对你修改的信息", reply_markup=ReplyKeyboardMarkup(reply_keyboard, True, True))
        return SEND_POST

    @staticmethod
    async def add_tags(update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> int:
        message = update.effective_message
        await message.reply_text(
            "请回复添加的tag名称，如果要添加多个tag请以空格作为分隔符，不用添加 # 作为开头，推送时程序会自动添加"
        )
        return GET_TAGS

    @conversation.state(state=GET_TAGS)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def get_tags(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        post_handler_data: PostHandlerData = context.chat_data.get("post_handler_data")
        message = update.effective_message
        args = message.text.split(" ")
        post_handler_data.tags = args
        await message.reply_text("添加成功")
        await message.reply_text("请选择你的操作", reply_markup=self.MENU_KEYBOARD)
        return CHECK_COMMAND

    @conversation.state(state=SEND_POST)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def send_post(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        post_handler_data: PostHandlerData = context.chat_data.get("post_handler_data")
        message = update.effective_message
        if message.text == "退出":
            await message.reply_text(text="退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        await message.reply_text("正在推送", reply_markup=ReplyKeyboardRemove())
        blocks: BlockList = post_handler_data.rich.blocks
        url = post_handler_data.url
        post_tags = post_handler_data.tags
        channel_id = post_handler_data.channel_id
        channel_name = None
        try:
            for channel_info in config.channels:
                if post_handler_data.channel_id == channel_info:
                    channel_name = await self.get_chat_username(chat_id=channel_id)
        except KeyError as exc:
            logger.error("从配置文件获取频道信息发生错误，退出任务")
            logger.exception(exc)
            await message.reply_text("从配置文件获取频道信息发生错误，退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        blocks.add_source_and_tags(url, channel_name, post_tags)
        try:
            await self.send_post_images(channel_id, None, post_handler_data.rich)
        except PyroBadRequest as exc:
            await message.reply_text(f"发送图片时发生错误 {exc.value}", reply_markup=ReplyKeyboardRemove())
            logger.error("Post模块发送图片时发生错误 %s", exc.value)
            return ConversationHandler.END
        except TypeError as exc:
            await message.reply_text("发送图片时发生错误，错误信息已经写到日记", reply_markup=ReplyKeyboardRemove())
            logger.error("Post模块发送图片时发生错误", exc_info=exc)
        await message.reply_text("推送成功", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    # ------------------------------------------------------------------
    # 旧版推送对话（/post_old）
    # ------------------------------------------------------------------
    @conversation.state(state=CHECK_COMMAND_OLD)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def check_command_old(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        message = update.effective_message
        if message.text == "退出":
            await message.reply_text("退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        if message.text == "推送频道":
            return await self.get_channel_old(update, context)
        if message.text == "添加TAG":
            return await self.add_tags_old(update, context)
        return ConversationHandler.END

    async def get_channel_old(self, update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> int:
        message = update.effective_message
        reply_keyboard = []
        try:
            for channel_id in config.channels:
                username = await self.get_chat_username(chat_id=channel_id)
                reply_keyboard.append([f"{username}"])
        except KeyError as error:
            logger.error("从配置文件获取频道信息发生错误，退出任务", exc_info=error)
            await message.reply_text("从配置文件获取频道信息发生错误，退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        await message.reply_text("请选择你要推送的频道", reply_markup=ReplyKeyboardMarkup(reply_keyboard, True, True))
        return GET_POST_CHANNEL_OLD

    @conversation.state(state=GET_POST_CHANNEL_OLD)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def get_post_channel_old(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        post_handler_data: PostHandlerData = context.chat_data.get("post_handler_data")
        message = update.effective_message
        channel_id = -1
        try:
            for channel_chat_id in config.channels:
                username = await self.get_chat_username(chat_id=channel_chat_id)
                if message.text == username:
                    channel_id = channel_chat_id
        except KeyError as exc:
            logger.error("从配置文件获取频道信息发生错误，退出任务", exc_info=exc)
            logger.exception(exc)
            await message.reply_text("从配置文件获取频道信息发生错误，退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        if channel_id == -1:
            await message.reply_text("获取频道信息失败，请检查你输入的内容是否正确", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        post_handler_data.old_channel_id = channel_id
        reply_keyboard = [["确认", "退出"]]
        await message.reply_text("请核对你修改的信息", reply_markup=ReplyKeyboardMarkup(reply_keyboard, True, True))
        return SEND_POST_OLD

    @staticmethod
    async def add_tags_old(update: "Update", _: "ContextTypes.DEFAULT_TYPE") -> int:
        message = update.effective_message
        await message.reply_text(
            "请回复添加的tag名称，如果要添加多个tag请以空格作为分隔符，不用添加 # 作为开头，推送时程序会自动添加"
        )
        return GET_TAGS

    @conversation.state(state=SEND_POST_OLD)
    @handler.message(filters=filters.TEXT & ~filters.COMMAND, block=False)
    async def send_post_old(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> int:
        post_handler_data: PostHandlerData = context.chat_data.get("post_handler_data")
        message = update.effective_message
        if message.text == "退出":
            await message.reply_text(text="退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        await message.reply_text("正在推送", reply_markup=ReplyKeyboardRemove())
        channel_id = post_handler_data.old_channel_id
        channel_name = None
        try:
            for channel_info in config.channels:
                if channel_id == channel_info:
                    channel_name = await self.get_chat_username(chat_id=channel_id)
        except KeyError as exc:
            logger.error("从配置文件获取频道信息发生错误，退出任务", exc_info=exc)
            logger.exception(exc)
            await message.reply_text("从配置文件获取频道信息发生错误，退出任务", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        post_text = post_handler_data.post_text
        post_images = []
        for index, _ in enumerate(post_handler_data.post_images):
            if index + 1 not in post_handler_data.delete_photo:
                post_images.append(post_handler_data.post_images[index])
        post_text += f" @{channel_name}"
        for tag in post_handler_data.tags:
            post_text += f" #{tag}"
        try:
            await self.send_post_old_images(channel_id, None, post_images, post_text)
        except PyroBadRequest as exc:
            await message.reply_text(f"发送图片时发生错误 {exc.value}", reply_markup=ReplyKeyboardRemove())
            logger.error("Post模块（旧版）发送图片时发生错误 %s", exc.value)
            return ConversationHandler.END
        except TypeError as exc:
            await message.reply_text("发送图片时发生错误，错误信息已经写到日记", reply_markup=ReplyKeyboardRemove())
            logger.error("Post模块（旧版）发送图片时发生错误", exc_info=exc)
        await message.reply_text("推送成功", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
