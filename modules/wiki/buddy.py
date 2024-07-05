from typing import List, Dict, Optional

from modules.wiki.base import WikiModel
from modules.wiki.models.buddy import Buddy as BuddyModel


class Buddy(WikiModel):
    buddy_url = WikiModel.BASE_URL + "buddy.json"
    buddy_path = WikiModel.BASE_PATH / "buddy.json"

    def __init__(self):
        super().__init__()
        self.all_buddys: List[BuddyModel] = []
        self.all_buddys_map: Dict[int, BuddyModel] = {}
        self.all_buddys_name: Dict[str, BuddyModel] = {}

    def clear_class_data(self) -> None:
        self.all_buddys.clear()
        self.all_buddys_map.clear()
        self.all_buddys_name.clear()

    async def refresh(self):
        datas = await self.remote_get(self.buddy_url)
        await self.dump(datas.json(), self.buddy_path)
        await self.read()

    async def read(self):
        if not self.buddy_path.exists():
            await self.refresh()
            return
        datas = await WikiModel.read(self.buddy_path)
        self.clear_class_data()
        for data in datas:
            m = BuddyModel(**data)
            self.all_buddys.append(m)
            self.all_buddys_map[m.id] = m
            self.all_buddys_name[m.name] = m

    def get_by_id(self, cid: int) -> Optional[BuddyModel]:
        return self.all_buddys_map.get(cid)

    def get_by_name(self, name: str) -> Optional[BuddyModel]:
        return self.all_buddys_name.get(name)

    def get_name_list(self) -> List[str]:
        return list(self.all_buddys_name.keys())
