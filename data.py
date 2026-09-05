"""داده‌ها و حافظه درون‌حافظه‌ای کلینیک (نسخه اولیه، بدون دیتابیس).

برنامه هفتگی پزشک در ``DEFAULT_SCHEDULE`` تعریف شده و نوبت‌های رزروشده
جدا از برنامه، در ``ClinicState.booked`` نگهداری می‌شوند.
"""

from __future__ import annotations

from dataclasses import dataclass

# برنامه هفتگی پزشک: کلید = روز، مقدار = لیست ساعت‌های پذیرش
DEFAULT_SCHEDULE: dict[str, list[str]] = {
    "شنبه": ["09:00", "10:00", "11:00"],
    "یکشنبه": ["09:00", "09:30", "10:30"],
    "دوشنبه": ["14:00", "15:00", "16:00"],
    "سه‌شنبه": ["09:00", "10:00", "11:00"],
}


@dataclass
class Appointment:
    """یک نوبت ثبت‌شده."""

    patient_name: str
    day: str
    time: str
    reason: str


class ClinicState:
    """حافظه کلینیک: برنامه هفتگی + نوبت‌های رزروشده (جدا از هم)."""

    def __init__(self, schedule: dict[str, list[str]] | None = None) -> None:
        # کپی از برنامه تا تغییرات، قالب پیش‌فرض را خراب نکند
        self.schedule: dict[str, list[str]] = {
            day: list(times) for day, times in (schedule or DEFAULT_SCHEDULE).items()
        }
        # کلید = "روز|ساعت" برای دسترسی سریع
        self.booked: dict[str, Appointment] = {}

    @staticmethod
    def slot_key(day: str, time: str) -> str:
        """کلید یکتای هر نوبت."""
        return f"{day}|{time}"

    def has_slot(self, day: str, time: str) -> bool:
        """آیا این زمان اصلاً در برنامه کلینیک وجود دارد؟"""
        return day in self.schedule and time in self.schedule[day]

    def available_times(self, day: str) -> list[str]:
        """ساعت‌های آزاد یک روز (برنامه منهای نوبت‌های رزروشده)."""
        booked_times = {appt.time for appt in self.booked.values() if appt.day == day}
        return [time for time in self.schedule.get(day, []) if time not in booked_times]

    def available_by_day(self) -> dict[str, list[str]]:
        """ساعت‌های آزاد همه روزها، به ترتیب تعریف برنامه."""
        return {day: self.available_times(day) for day in self.schedule}

    def first_free(self) -> dict[str, str] | None:
        """نزدیک‌ترین نوبت آزاد (اولین روز/ساعت آزاد در ترتیب برنامه)."""
        for day, times in self.available_by_day().items():
            if times:
                return {"day": day, "time": times[0]}
        return None

    def book(self, patient_name: str, day: str, time: str, reason: str) -> Appointment:
        """ثبت نوبت در حافظه (اعتبارسنجی در لایه tools انجام می‌شود)."""
        appointment = Appointment(
            patient_name=patient_name,
            day=day,
            time=time,
            reason=reason,
        )
        self.booked[self.slot_key(day, time)] = appointment
        return appointment
