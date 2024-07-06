from datetime import timedelta

from influxdb_client import Point
from influxdb_client.client.flux_table import FluxRecord
from simnet.models.zzz.self_help import ZZZSelfHelpActionLog

from modules.action_log.date import TZ

FIX = timedelta(minutes=6)


class ActionLogModel:
    @staticmethod
    def en(data: "ZZZSelfHelpActionLog") -> Point:
        return (
            Point.measurement("action_log")
            .tag("uid", data.uid)
            .field("id", data.id)
            .field("status", data.status)
            .field("reason", data.reason.value)
            .field("client_ip", data.client_ip)
            .time(data.time.replace(tzinfo=TZ) + FIX)
        )

    @staticmethod
    def de(data: "FluxRecord") -> "ZZZSelfHelpActionLog":
        utc_time = data.get_time()
        time = utc_time.astimezone(TZ)
        return ZZZSelfHelpActionLog(
            id=data["id"], uid=data["uid"], datetime=time, action_name=data["reason"], client_ip=data["client_ip"]
        )
