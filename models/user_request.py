from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


VibeName = Literal[
    "Chữa lành & Yên bình",
    "Đậm văn hóa & Bản địa",
    "Sáng tạo & Truyền cảm hứng",
    "Năng động & Phiêu lưu",
    "Trải nghiệm đa dạng",
]

RegionName = Literal[
    "Thừa Thiên Huế",
    "Đà Nẵng",
    "Quảng Nam",
]


class UserRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    duration: int = Field(
        default=1,
        ge=1,
        le=14,
        strict=True,
        description="Số ngày của hành trình, từ 1 đến 14.",
        examples=[2],
    )
    vibe: VibeName = Field(
        description="Phong cách trải nghiệm mong muốn.",
        examples=["Chữa lành & Yên bình"],
    )
    region: RegionName = Field(
        description="Tỉnh/thành phố của hành trình.",
        examples=["Quảng Nam"],
    )
    max_places_per_day: int = Field(
        default=5,
        ge=1,
        le=6,
        strict=True,
        description="Số địa điểm tối đa trong một ngày, từ 1 đến 6.",
        examples=[5],
    )
    max_daily_distance_km: float = Field(
        default=20.0,
        gt=0,
        le=100,
        description="Tổng quãng đường tối đa giữa các điểm trong một ngày.",
        examples=[20.0],
    )
    preferred_activities: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Các nhóm hoạt động ưu tiên, ví dụ Ẩm thực hoặc "
            "Thiên nhiên & Ngắm cảnh."
        ),
        examples=[["Ẩm thực", "Tham quan & Khám phá"]],
    )
    start_date: date = Field(
        description="Ngày bắt đầu hành trình theo định dạng YYYY-MM-DD.",
        examples=["2026-08-01"],
    )
    day_start_time: time = Field(
        default=time(8, 0),
        description="Giờ bắt đầu mỗi ngày theo định dạng HH:MM.",
        examples=["08:00"],
    )
    day_end_time: time = Field(
        default=time(21, 0),
        description="Giờ kết thúc mỗi ngày theo định dạng HH:MM.",
        examples=["21:00"],
    )

    @model_validator(mode="after")
    def validate_daily_time_window(self):
        if self.day_end_time <= self.day_start_time:
            raise ValueError(
                "day_end_time phải muộn hơn day_start_time trong cùng ngày"
            )
        return self
