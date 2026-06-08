"""从 Quill Delta JSON 格式解析为 Telegram PageBlock 列表。

仿造 :mod:`defs.rich_text` 的设计，把 Quoted (Quill) 的 ``delta`` JSON 文档
（由 ``defs/1.json`` 这类结构描述）转换为 ``BlockList`` 形式的 Telegram 原生
PageBlock 列表以及待上传的 ``PhotoType`` 列表。

主要入口：:func:`json_to_blocks`。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pyrogram import raw

# 用于“换行产生空段落”的占位文本——Telegram 端的 PageBlockParagraph
# 实际上不允许空 text，这里使用单个半角空格保持渲染稳定。
_EMPTY_LINE_PLACEHOLDER = " "


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
class PhotoType(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    id: int
    src: str
    block: raw.types.PageBlockPhoto | raw.types.PageBlockVideo
    slide: raw.types.PageBlockSlideshow | None = None

    is_gif: bool = False
    is_video: bool = False


class BlockList(list["raw.base.PageBlock"]):
    def add_title(self, title: str):
        header = raw.types.PageBlockHeading1(text=raw.types.TextPlain(text=title))
        self.insert(0, header)

    def add_source_and_tags(self, url: str, username: str, post_tags: list[str]) -> None:
        text_url = raw.types.TextUrl(text=raw.types.TextPlain(text="source"), url=url, webpage_id=0)
        username = raw.types.TextPlain(text=f" @{username} ")
        post_tags_str = " "
        if post_tags:
            post_tags_str = "".join([f" #{tag}" for tag in post_tags])
        text_tags = raw.types.TextPlain(text=post_tags_str)
        concat = raw.types.TextConcat(texts=[text_url, username, text_tags])
        br = raw.types.PageBlockParagraph(text=raw.types.TextPlain(text=" "))
        self.append(br)
        self.append(raw.types.PageBlockParagraph(text=concat))

    def fix_photo_block(self, new_photo: list[PhotoType]) -> None:
        """根据上传后的图片信息修正 PageBlock 列表中的图片块。

        遍历 ``self`` 中的每个 ``PageBlockPhoto``，根据对应 ``PhotoType`` 的
        上传结果进行如下处理：

        1. 当 ``self`` 中某 ``PageBlockPhoto`` 与 ``new_photo`` 中该 ``src`` 唯一
           对应时，直接把 ``photo_id`` 更新为上传后的真实 ID。
        2. 当同一 ``src`` 在 ``self`` 中对应多个 ``PageBlockPhoto``、且
           ``new_photo`` 中也提供了多条不同 ID 的记录时，将这些连续的
           ``PageBlockPhoto`` 合并为 ``PageBlockSlideshow``，便于在 Telegram
           内进行多图翻页展示。
        3. 当 ``PhotoType.is_gif`` 或 ``is_video`` 为真时，将对应位置的
           ``PageBlockPhoto`` 替换为 ``PageBlockVideo``，并把 ``video_id``
           更新为上传后的真实 ID。
        """
        # 1. 处理视频/GIF：把对应位置的 PageBlockPhoto 替换为 PageBlockVideo
        for photo in new_photo:
            if not (photo.is_gif or photo.is_video):
                continue
            block = photo.block
            if not isinstance(block, raw.types.PageBlockPhoto):
                continue
            # 使用对象身份查找位置，避免 PageBlockPhoto.__eq__ 误判
            idx = -1
            for i, blk in enumerate(self):
                if blk is block:
                    idx = i
                    break
            if idx < 0:
                continue
            new_block = raw.types.PageBlockVideo(
                video_id=photo.id,
                caption=block.caption,
            )
            self[idx] = new_block
            photo.block = new_block

        # 2. 按 src 聚合剩余的 PageBlockPhoto
        # 调用方需保证：同一 src 对应的 PageBlockPhoto 在 self 中是连续片段。
        photos_by_src: dict[str, list[PhotoType]] = {}
        for photo in new_photo:
            if photo.is_gif or photo.is_video:
                # 已经在上一步处理过
                continue
            if not isinstance(photo.block, raw.types.PageBlockPhoto):
                continue
            # 使用对象身份校验 block 存在于 self
            found = False
            for blk in self:
                if blk is photo.block:
                    found = True
                    break
            if not found:
                continue
            photos_by_src.setdefault(photo.src, []).append(photo)

        for src, photos in photos_by_src.items():
            if not photos:
                continue
            # 找到这些 photos 对应的 block 在 self 中的下标
            # 使用 id() 比较对象身份，避免 PageBlockPhoto 因 photo_id=0 占位
            # 而被 __eq__ 误判为相等、导致 self.index 始终返回首个下标。
            idx = -1
            for i, blk in enumerate(self):
                if blk is photos[0].block:
                    idx = i
                    break
            if idx < 0:
                continue
            # 唯一对应：直接更新 photo_id
            if len(photos) == 1:
                photos[0].block.photo_id = photos[0].id
                continue
            # 不唯一：要求这些 block 在 self 中是连续片段，否则无法合并为 Slideshow
            # 合并为 PageBlockSlideshow
            blocks = []
            for i in photos:
                p = raw.types.PageBlockPhoto(photo_id=i.id, caption=_make_caption(""))
                i.block = p
                blocks.append(p)
            slideshow = raw.types.PageBlockSlideshow(
                items=blocks,
                caption=_make_caption(""),
            )
            self[idx] = slideshow
            for p in photos:
                p.slide = slideshow

    def merge_adjacent_photo_blocks(self) -> None:
        """把相邻的 PageBlockPhoto / PageBlockVideo / PageBlockSlideshow 合并为单个 PageBlockSlideshow。

        遍历 ``self``，把由非图片/非幻灯片子节点分隔的连续片段（每个片段由
        ``PageBlockPhoto`` / ``PageBlockVideo`` / ``PageBlockSlideshow`` 组成）
        统一合并为一个 ``PageBlockSlideshow``：

        - 片段内只有单个节点：保持原状，不做改动。
        - 片段内有多个节点：按出现顺序把 ``PageBlockSlideshow`` 内的 ``items``
          摊平后，与零散的 ``PageBlockPhoto`` / ``PageBlockVideo`` 一起作为新
          ``PageBlockSlideshow.items``。

        该方法应当在 ``fix_photo_block`` 之后、``ignore_invalid_photo_block``
        之前调用，确保所有 ``photo_id`` / ``video_id`` 已经是上传后的真实 ID。
        """
        merged: list[raw.base.PageBlock] = []
        buffer: list[raw.base.PageBlock] = []

        def _flush() -> None:
            if not buffer:
                return
            if len(buffer) == 1:
                merged.append(buffer[0])
                buffer.clear()
                return
            items: list[raw.base.PageBlock] = []
            for blk in buffer:
                if isinstance(blk, raw.types.PageBlockSlideshow):
                    items.extend(blk.items)
                else:
                    items.append(blk)
            _caption = caption = raw.types.PageCaption(
                text=raw.types.TextEmpty(),
                credit=raw.types.TextEmpty(),
            )
            # 尽量保留首个非空 caption
            for blk in buffer:
                cap = getattr(blk, "caption", None)
                if cap is not None and not (isinstance(cap.text, raw.types.TextEmpty) and not cap.credit):
                    caption = cap
                    break
            merged.append(raw.types.PageBlockSlideshow(items=items, caption=caption or _caption))
            buffer.clear()

        for blk in self:
            if isinstance(blk, (raw.types.PageBlockPhoto, raw.types.PageBlockVideo)) or isinstance(
                blk, raw.types.PageBlockSlideshow
            ):
                buffer.append(blk)
            else:
                _flush()
                merged.append(blk)
        _flush()

        self[:] = merged

    def ignore_invalid_photo_block(self) -> None:
        """从当前列表中移除尚未成功上传/解析的占位图片/视频块。

        遍历 ``self``，删除所有 ``photo_id`` 或 ``video_id`` 仍为 ``0`` 的
        ``PageBlockPhoto`` / ``PageBlockVideo`` 节点。``PageBlockSlideshow``
        中的子项若仍为占位也会被同步剔除，确保最终发往 Telegram 的 block
        列表中不包含无效 ID。
        """
        # 1. 清理顶层的 PageBlockPhoto / PageBlockVideo
        kept: list[raw.base.PageBlock] = []
        for blk in self:
            if isinstance(blk, raw.types.PageBlockPhoto) and blk.photo_id == 0:
                continue
            if isinstance(blk, raw.types.PageBlockVideo) and blk.video_id == 0:
                continue
            kept.append(blk)
        # 就地替换内容
        self[:] = kept

        # 2. 清理 PageBlockSlideshow 内部的占位子项
        for i, blk in enumerate(self):
            if not isinstance(blk, raw.types.PageBlockSlideshow):
                continue
            new_items = [
                item
                for item in blk.items
                if not (
                    (isinstance(item, raw.types.PageBlockPhoto) and item.photo_id == 0)
                    or (isinstance(item, raw.types.PageBlockVideo) and item.video_id == 0)
                )
            ]
            if len(new_items) != len(blk.items):
                # 重建 Slideshow 以保证 items 与实际过滤结果一致
                self[i] = raw.types.PageBlockSlideshow(
                    items=new_items,
                    caption=blk.caption,
                )


class _Op(BaseModel):
    """Quill Delta 中的单条操作。"""

    model_config = {"arbitrary_types_allowed": True}

    insert: str | dict[str, Any]
    attributes: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# 工具方法
# ---------------------------------------------------------------------------


def _make_rich_text(text: str) -> raw.base.RichText:
    """构造纯文本 RichText 节点。空内容返回 TextEmpty。"""
    if not text:
        return raw.types.TextEmpty()
    return raw.types.TextPlain(text=text)


def _make_caption(text: str) -> raw.types.PageCaption:
    """构造图片说明 PageCaption。"""
    return raw.types.PageCaption(text=_make_rich_text(text), credit=raw.types.TextEmpty())


def _split_paragraphs(ops: list[_Op]) -> list[list[_Op]]:
    """按 ``\\n`` 把 ops 拆成多个段落。

    Quill 中每个 ``\\n`` 都是段落分隔：连续两个 ``\\n`` 会产生一个空段。
    一段 op 中可能含图片，图片由调用方进一步处理。
    """
    paragraphs: list[list[_Op]] = []
    current: list[_Op] = []
    for op in ops:
        if isinstance(op.insert, str) and "\n" in op.insert:
            parts = op.insert.split("\n")
            for i, part in enumerate(parts):
                if i > 0:
                    # 遇到 \n：先提交当前段落
                    paragraphs.append(current)
                    current = []
                if part:
                    current.append(_Op(insert=part, attributes=op.attributes))
            # 连续 \n 时 current 仍可能是空列表，下次遇到 \n 会作为一个空段被提交
        else:
            current.append(op)
    if current:
        paragraphs.append(current)
    return paragraphs


def _extract_media_url(op: _Op) -> str | None:
    """从 op 中提取需要作为图片展示的媒体 URL。

    支持的 insert 形式：

    - ``{"image": "<url>"}`` —— 直接图片。
    - ``{"vod": {"cover": "<url>", ...}}`` —— 米游社视频节点，统一使用
      ``cover`` 作为缩略图展示，不当作视频解析。
    """
    if not isinstance(op.insert, dict):
        return None
    if "image" in op.insert:
        url = op.insert.get("image")
        return url if isinstance(url, str) and url else None
    if "vod" in op.insert:
        vod = op.insert.get("vod")
        if isinstance(vod, dict):
            cover = vod.get("cover")
            if isinstance(cover, str) and cover:
                return cover
    return None


def _is_fold_op(op: _Op) -> bool:
    """判断 op 是否为 ``insert.fold`` 折叠节点。"""
    return isinstance(op.insert, dict) and "fold" in op.insert


def _parse_fold_payload(payload: str) -> list[_Op]:
    """解析 ``fold.title`` / ``fold.content`` 中的内嵌 JSON 字符串为 op 列表。

    内嵌字段本身是一段 JSON 字符串（形如 ``'[{"insert": ...}]'``），需要先
    ``json.loads`` 后再转换为 :class:`_Op`。当 JSON 解析失败时返回空列表，
    由调用方按"无可展开内容"处理。
    """
    import json

    if not isinstance(payload, str) or not payload:
        return []
    try:
        raw_ops = json.loads(payload)
    except (ValueError, TypeError):
        return []
    if not isinstance(raw_ops, list):
        return []
    return [_Op.model_validate(o) for o in raw_ops]


def _op_text_pieces(op: _Op) -> list[raw.base.RichText]:
    """把单条文本 op 转换为 RichText 列表（按属性逐个包一层）。"""
    if not isinstance(op.insert, str) or not op.insert:
        return []
    base = _make_rich_text(op.insert)
    attrs = op.attributes or {}
    # 处理链接
    if "link" in attrs and isinstance(attrs["link"], str):
        base = raw.types.TextUrl(text=base, url=attrs["link"], webpage_id=0)
    # 处理加粗
    if attrs.get("bold"):
        base = raw.types.TextBold(text=base)
    return [base]


def _make_paragraph_block(ops: list[_Op]) -> raw.types.PageBlockParagraph:
    """把一段 op 列表合并为 PageBlockParagraph。

    段落为空时返回包含空格的占位段，以保持 Telegram 端的渲染稳定。
    """
    pieces: list[raw.base.RichText] = []
    for op in ops:
        pieces.extend(_op_text_pieces(op))
    if not pieces:
        return raw.types.PageBlockParagraph(text=_make_rich_text(_EMPTY_LINE_PLACEHOLDER))
    if len(pieces) == 1:
        return raw.types.PageBlockParagraph(text=pieces[0])
    return raw.types.PageBlockParagraph(text=raw.types.TextConcat(texts=pieces))


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def json_to_blocks(data: list[dict[str, Any]] | dict[str, Any]) -> tuple[BlockList, list[PhotoType]]:
    """把 Quill Delta JSON 数据转换为 Telegram PageBlock 列表与待上传图片。

    Args:
        data: 形如 ``[{"insert": "..."}, {"insert": {"image": "url"}, ...}]`` 的
            Quill Delta 数据，也可以是 ``{"ops": [...]}`` 形式。

    Returns:
        ``(blocks, photos)``。``blocks`` 是 :class:`BlockList`，可直接传入
        ``BlockList`` 的方法进行后续处理；``photos`` 是 ``PhotoType`` 列表，
        其中 ``block`` 字段指向 ``PageBlockPhoto``，后续由调用方上传并通过
        ``fix_photo_block`` 修正 ID。

    Notes:
        - ``insert.fold`` 节点中的 ``title`` 和 ``content`` 是内嵌的 JSON 字符串，
          会被递归解析并按出现顺序 inline 展开到主 block 列表中（不做折叠/收起，
          直接把所有图片等块展开为顶层 block）。
        - ``insert.vod`` 节点使用 ``cover`` 字段作为图片展示。
    """
    # 统一从 dict 中取出 ops
    if isinstance(data, dict) and "ops" in data:
        ops_raw = data["ops"]
    else:
        ops_raw = data
    ops = [_Op.model_validate(o) for o in ops_raw]

    blocks: BlockList = BlockList()
    photos: list[PhotoType] = []

    def _render(op_list: list[_Op]) -> None:
        """递归把 op 列表展开为 block 并追加到 ``blocks``。"""
        paragraphs = _split_paragraphs(op_list)
        for para_ops in paragraphs:
            if not para_ops:
                # 连续 \n 产生的空段落
                blocks.append(raw.types.PageBlockParagraph(text=_make_rich_text(_EMPTY_LINE_PLACEHOLDER)))
                continue

            pending_text: list[_Op] = []
            for op in para_ops:
                # 1. fold 节点：递归展开 title + content
                if _is_fold_op(op):
                    if pending_text:
                        blocks.append(_make_paragraph_block(pending_text))
                        pending_text = []
                    fold = op.insert.get("fold") or {}
                    if not isinstance(fold, dict):
                        continue
                    title_ops = _parse_fold_payload(fold.get("title", ""))
                    content_ops = _parse_fold_payload(fold.get("content", ""))
                    if title_ops:
                        _render(title_ops)
                    if content_ops:
                        _render(content_ops)
                    continue

                # 2. 图片节点
                url = _extract_media_url(op)
                if url is not None:
                    if pending_text:
                        blocks.append(_make_paragraph_block(pending_text))
                        pending_text = []
                    photo_block = raw.types.PageBlockPhoto(
                        photo_id=0,
                        caption=_make_caption(""),
                    )
                    photos.append(PhotoType(id=0, src=url, block=photo_block))
                    blocks.append(photo_block)
                    continue

                # 3. 文本 op
                pending_text.append(op)

            if pending_text:
                blocks.append(_make_paragraph_block(pending_text))

    _render(ops)
    return blocks, photos
