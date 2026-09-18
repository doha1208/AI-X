from datetime import datetime, time, timedelta, timezone
from typing import Literal

Period = Literal["day", "night"]

# 한국은 서머타임이 없어 IANA tzdata 없이도(Windows 포함) 정확한 고정 오프셋.
KST = timezone(timedelta(hours=9))

NIGHT_START = time(22, 0)
NIGHT_END = time(6, 0)


def period_for(at: datetime | None = None) -> Period:
    """KST 기준 22:00~06:00을 야간(night)으로 판정한다.

    ponytail: 주/야간 2단계 MVP — 필요해지면 새벽 등으로 세분화.
    """
    moment = at if at is not None else datetime.now(KST)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=KST)
    local_time = moment.astimezone(KST).time()
    is_night = local_time >= NIGHT_START or local_time < NIGHT_END
    return "night" if is_night else "day"
