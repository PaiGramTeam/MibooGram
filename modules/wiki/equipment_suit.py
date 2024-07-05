from typing import List, Dict, Optional

from modules.wiki.base import WikiModel
from modules.wiki.models.equipment_suit import EquipmentSuit as EquipmentSuitModel


class EquipmentSuit(WikiModel):
    equipment_suit_url = WikiModel.BASE_URL + "equipment_suits.json"
    equipment_suit_path = WikiModel.BASE_PATH / "equipment_suits.json"

    def __init__(self):
        super().__init__()
        self.all_equipment_suits: List[EquipmentSuitModel] = []
        self.all_equipment_suits_map: Dict[int, EquipmentSuitModel] = {}
        self.all_equipment_suits_name: Dict[str, EquipmentSuitModel] = {}

    def clear_class_data(self) -> None:
        self.all_equipment_suits.clear()
        self.all_equipment_suits_map.clear()
        self.all_equipment_suits_name.clear()

    async def refresh(self):
        datas = await self.remote_get(self.equipment_suit_url)
        await self.dump(datas.json(), self.equipment_suit_path)
        await self.read()

    async def read(self):
        if not self.equipment_suit_path.exists():
            await self.refresh()
            return
        datas = await WikiModel.read(self.equipment_suit_path)
        self.clear_class_data()
        for data in datas:
            m = EquipmentSuitModel(**data)
            self.all_equipment_suits.append(m)
            self.all_equipment_suits_map[m.id] = m
            self.all_equipment_suits_name[m.name] = m

    def get_by_id(self, cid: int) -> Optional[EquipmentSuitModel]:
        return self.all_equipment_suits_map.get(cid)

    def get_by_name(self, name: str) -> Optional[EquipmentSuitModel]:
        return self.all_equipment_suits_name.get(name)

    def get_name_list(self) -> List[str]:
        return list(self.all_equipment_suits_name.keys())
