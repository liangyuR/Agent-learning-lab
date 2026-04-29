from datetime import datetime
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field

from tools.base_tool import BaseTool


class GetCurrentTimeArgs(BaseModel):
    timezone: str = Field(default="Asia/Shanghai")


class GetCurrentTimeTool(BaseTool):
    name = "get_current_time"
    description = "获取指定时区的当前时间"
    input_model = GetCurrentTimeArgs

    def run(self, args: GetCurrentTimeArgs) -> dict:
        now = datetime.now(ZoneInfo(args.timezone))
        return {
            "timezone": args.timezone,
            "datetime": now.isoformat(),
            "date": now.date().isoformat(),
            "time": now.strftime("%H:%M:%S"),
        }