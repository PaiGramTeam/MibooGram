from datetime import datetime, timedelta

from pydantic import BaseModel
from simnet.models.zzz.self_help import ZZZSelfHelpActionLog


class ActionLogPair(BaseModel):
    start: ZZZSelfHelpActionLog
    end: ZZZSelfHelpActionLog

    @property
    def start_time(self) -> datetime:
        return self.start.time

    @property
    def end_time(self) -> datetime:
        return self.end.time

    @property
    def duration(self) -> timedelta:
        return self.end.time - self.start.time
