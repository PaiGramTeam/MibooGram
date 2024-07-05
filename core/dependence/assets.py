import asyncio
from pathlib import Path
from ssl import SSLZeroReturnError
from typing import Optional, List, Dict

from aiofiles import open as async_open
from httpx import AsyncClient, HTTPError

from core.base_service import BaseService
from modules.wiki.base import WikiModel
from modules.wiki.models.avatar import Avatar
from modules.wiki.models.weapon import Weapon
from modules.wiki.models.buddy import Buddy
from modules.wiki.models.equipment_suit import EquipmentSuit
from utils.const import PROJECT_ROOT
from utils.log import logger
from utils.typedefs import StrOrURL, StrOrInt

ASSETS_PATH = PROJECT_ROOT.joinpath("resources/assets")
ASSETS_PATH.mkdir(exist_ok=True, parents=True)
DATA_MAP = {
    "avatar": WikiModel.BASE_URL + "avatars.json",
    "weapon": WikiModel.BASE_URL + "weapons.json",
    "buddy": WikiModel.BASE_URL + "buddy.json",
    "equipment_suit": WikiModel.BASE_URL + "equipment_suits.json",
}


class AssetsServiceError(Exception):
    pass


class AssetsCouldNotFound(AssetsServiceError):
    def __init__(self, message: str, target: str):
        self.message = message
        self.target = target
        super().__init__(f"{message}: target={target}")


class _AssetsService:
    client: Optional[AsyncClient] = None

    def __init__(self, client: Optional[AsyncClient] = None) -> None:
        self.client = client

    async def _download(self, url: StrOrURL, path: Path, retry: int = 5) -> Optional[Path]:
        """从 url 下载图标至 path"""
        if not url:
            return None
        logger.debug("正在从 %s 下载图标至 %s", url, path)
        headers = None
        for time in range(retry):
            try:
                response = await self.client.get(url, follow_redirects=False, headers=headers)
            except Exception as error:  # pylint: disable=W0703
                if not isinstance(error, (HTTPError, SSLZeroReturnError)):
                    logger.error(error)  # 打印未知错误
                if time != retry - 1:  # 未达到重试次数
                    await asyncio.sleep(1)
                else:
                    raise error
                continue
            if response.status_code != 200:  # 判定页面是否正常
                return None
            async with async_open(path, "wb") as file:
                await file.write(response.content)  # 保存图标
            return path.resolve()


class _AvatarAssets(_AssetsService):
    path: Path
    data: List[Avatar]
    name_map: Dict[str, Avatar]
    id_map: Dict[int, Avatar]

    def __init__(self, client: Optional[AsyncClient] = None) -> None:
        super().__init__(client)
        self.path = ASSETS_PATH.joinpath("agent")
        self.path.mkdir(exist_ok=True, parents=True)

    async def initialize(self):
        logger.info("正在初始化角色素材图标")
        html = await self.client.get(DATA_MAP["avatar"])
        self.data = [Avatar(**data) for data in html.json()]
        self.name_map = {icon.name: icon for icon in self.data}
        self.id_map = {icon.id: icon for icon in self.data}
        tasks = []
        for icon in self.data:
            base_path = self.path / f"{icon.id}"
            base_path.mkdir(exist_ok=True, parents=True)
            gacha_path = base_path / "gacha.png"
            icon_path = base_path / "icon.png"
            normal_path = base_path / "normal.png"
            if not gacha_path.exists():
                tasks.append(self._download(icon.gacha, gacha_path))
            if not icon_path.exists():
                tasks.append(self._download(icon.icon_, icon_path))
            if not normal_path.exists():
                tasks.append(self._download(icon.normal, normal_path))

            if len(tasks) >= 100:
                await asyncio.gather(*tasks)
                tasks = []
        if tasks:
            await asyncio.gather(*tasks)
        logger.info("角色素材图标初始化完成")

    def get_path(self, icon: Avatar, name: str, ext: str = "png") -> Path:
        path = self.path / f"{icon.id}"
        path.mkdir(exist_ok=True, parents=True)
        return path / f"{name}.{ext}"

    def get_by_id(self, id_: int) -> Optional[Avatar]:
        return self.id_map.get(id_, None)

    def get_by_name(self, name: str) -> Optional[Avatar]:
        return self.name_map.get(name, None)

    def get_target(self, target: StrOrInt, second_target: StrOrInt = None) -> Avatar:
        data = None
        if isinstance(target, int):
            data = self.get_by_id(target)
        elif isinstance(target, str):
            data = self.get_by_name(target)
        if data is None:
            if second_target:
                return self.get_target(second_target)
            raise AssetsCouldNotFound("角色素材图标不存在", target)
        return data

    def gacha(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "gacha")

    def icon(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "icon")

    def normal(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "normal")


class _WeaponAssets(_AssetsService):
    path: Path
    data: List[Weapon]
    name_map: Dict[str, Weapon]
    id_map: Dict[int, Weapon]

    def __init__(self, client: Optional[AsyncClient] = None) -> None:
        super().__init__(client)
        self.path = ASSETS_PATH.joinpath("engines")
        self.path.mkdir(exist_ok=True, parents=True)

    async def initialize(self):
        logger.info("正在初始化武器素材图标")
        html = await self.client.get(DATA_MAP["weapon"])
        self.data = [Weapon(**data) for data in html.json()]
        self.name_map = {icon.name: icon for icon in self.data}
        self.id_map = {icon.id: icon for icon in self.data}
        tasks = []
        for icon in self.data:
            base_path = self.path / f"{icon.id}"
            base_path.mkdir(exist_ok=True, parents=True)
            icon_path = base_path / "icon.webp"
            if not icon_path.exists():
                tasks.append(self._download(icon.icon, icon_path))
            if len(tasks) >= 100:
                await asyncio.gather(*tasks)
                tasks = []
        if tasks:
            await asyncio.gather(*tasks)
        logger.info("武器素材图标初始化完成")

    def get_path(self, icon: Weapon, name: str) -> Path:
        path = self.path / f"{icon.id}"
        path.mkdir(exist_ok=True, parents=True)
        return path / f"{name}.webp"

    def get_by_id(self, id_: int) -> Optional[Weapon]:
        return self.id_map.get(id_, None)

    def get_by_name(self, name: str) -> Optional[Weapon]:
        return self.name_map.get(name, None)

    def get_target(self, target: StrOrInt, second_target: StrOrInt = None) -> Optional[Weapon]:
        if isinstance(target, int):
            return self.get_by_id(target)
        elif isinstance(target, str):
            return self.get_by_name(target)
        if second_target:
            return self.get_target(second_target)
        raise AssetsCouldNotFound("武器素材图标不存在", target)

    def icon(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "icon")


class _BuddyAssets(_AssetsService):
    path: Path
    data: List[Buddy]
    id_map: Dict[int, Buddy]
    name_map: Dict[str, Buddy]

    def __init__(self, client: Optional[AsyncClient] = None) -> None:
        super().__init__(client)
        self.path = ASSETS_PATH.joinpath("buddy")
        self.path.mkdir(exist_ok=True, parents=True)

    async def initialize(self):
        logger.info("正在初始化邦布素材图标")
        html = await self.client.get(DATA_MAP["buddy"])
        self.data = [Buddy(**data) for data in html.json()]
        self.id_map = {icon.id: icon for icon in self.data}
        self.name_map = {icon.name: icon for icon in self.data}
        tasks = []
        for icon in self.data:
            webp_path = self.path / f"{icon.id}.webp"
            png_path = self.path / f"{icon.id}.png"
            if not webp_path.exists() and icon.webp:
                tasks.append(self._download(icon.webp, webp_path))
            if not png_path.exists() and icon.png:
                tasks.append(self._download(icon.png, png_path))
            if len(tasks) >= 100:
                await asyncio.gather(*tasks)
                tasks = []
        if tasks:
            await asyncio.gather(*tasks)
        logger.info("邦布素材图标初始化完成")

    def get_path(self, icon: Buddy, ext: str) -> Path:
        path = self.path / f"{icon.id}.{ext}"
        return path

    def get_by_id(self, id_: int) -> Optional[Buddy]:
        return self.id_map.get(id_, None)

    def get_by_name(self, name: str) -> Optional[Buddy]:
        return self.name_map.get(name, None)

    def get_target(self, target: StrOrInt, second_target: StrOrInt = None) -> Optional[Buddy]:
        if isinstance(target, int):
            return self.get_by_id(target)
        elif isinstance(target, str):
            return self.get_by_name(target)
        if second_target:
            return self.get_target(second_target)
        raise AssetsCouldNotFound("邦布素材图标不存在", target)

    def webp(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "webp")

    def png(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        return self.get_path(icon, "png")

    def icon(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        icon = self.get_target(target, second_target)
        webp_path = self.get_path(icon, "webp")
        png_path = self.get_path(icon, "png")
        if webp_path.exists():
            return webp_path
        if png_path.exists():
            return png_path
        raise AssetsCouldNotFound("邦布素材图标不存在", target)


class _EquipmentSuitAssets(_AssetsService):
    path: Path
    data: List[EquipmentSuit]
    id_map: Dict[int, EquipmentSuit]
    name_map: Dict[str, EquipmentSuit]

    def __init__(self, client: Optional[AsyncClient] = None) -> None:
        super().__init__(client)
        self.path = ASSETS_PATH.joinpath("equipment_suit")
        self.path.mkdir(exist_ok=True, parents=True)

    async def initialize(self):
        logger.info("正在初始化驱动盘素材图标")
        html = await self.client.get(DATA_MAP["equipment_suit"])
        self.data = [EquipmentSuit(**data) for data in html.json()]
        self.id_map = {theme.id: theme for theme in self.data}
        self.name_map = {theme.name: theme for theme in self.data}
        tasks = []
        for theme in self.data:
            path = self.path / f"{theme.id}.webp"
            if not path.exists():
                tasks.append(self._download(theme.icon, path))
            if len(tasks) >= 100:
                await asyncio.gather(*tasks)
                tasks = []
        if tasks:
            await asyncio.gather(*tasks)
        logger.info("驱动盘素材图标初始化完成")

    def get_path(self, theme: EquipmentSuit, ext: str) -> Path:
        path = self.path / f"{theme.id}.{ext}"
        return path

    def get_by_id(self, id_: int) -> Optional[EquipmentSuit]:
        return self.id_map.get(id_, None)

    def get_by_name(self, name_: str) -> Optional[EquipmentSuit]:
        return self.name_map.get(name_, None)

    def get_target(self, target: StrOrInt, second_target: StrOrInt = None) -> Optional[EquipmentSuit]:
        if isinstance(target, int):
            return self.get_by_id(target)
        elif isinstance(target, str):
            return self.get_by_name(target)
        if second_target:
            return self.get_target(second_target)
        raise AssetsCouldNotFound("驱动盘素材图标不存在", target)

    def icon(self, target: StrOrInt, second_target: StrOrInt = None) -> Path:
        theme = self.get_target(target, second_target)
        webp_path = self.get_path(theme, "webp")
        if webp_path.exists():
            return webp_path
        raise AssetsCouldNotFound("驱动盘素材图标不存在", target)


class AssetsService(BaseService.Dependence):
    """asset服务

    用于储存和管理 asset :
        当对应的 asset (如某角色图标)不存在时，该服务会先查找本地。
        若本地不存在，则从网络上下载；若存在，则返回其路径
    """

    client: Optional[AsyncClient] = None

    avatar: _AvatarAssets
    """角色"""

    weapon: _WeaponAssets
    """武器"""

    buddy: _BuddyAssets
    """邦布"""

    equipment_suit: _EquipmentSuitAssets
    """驱动盘"""

    def __init__(self):
        self.client = AsyncClient(timeout=60.0)
        self.avatar = _AvatarAssets(self.client)
        self.weapon = _WeaponAssets(self.client)
        self.buddy = _BuddyAssets(self.client)
        self.equipment_suit = _EquipmentSuitAssets(self.client)

    async def initialize(self):  # pylint: disable=W0221
        await self.avatar.initialize()
        await self.weapon.initialize()
        await self.buddy.initialize()
        await self.equipment_suit.initialize()
