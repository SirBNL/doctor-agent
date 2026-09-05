"""ابزارهای (Tools) در دسترس Agent.

این ماژول دو Tool اصلی Agent را تعریف می‌کند:

    1) get_available_slots  → دیدن زمان‌های آزاد پزشک
    2) book_appointment     → ثبت نوبت

Docstring هر تابع عمداً بسیار دقیق نوشته شده است، چون کتابخانه ollama همان را
به‌عنوان توضیحات Tool به مدل نشان می‌دهد و مدل فقط بر اساس آن تصمیم می‌گیرد
کِی و با چه آرگومان‌هایی Tool را صدا بزند.

اجرای Toolها فقط از طریق ``TOOL_REGISTRY`` (mapping امن) انجام می‌شود؛
از eval() یا اجرای داینامیک خطرناک خبری نیست و هیچ خطای Tool باعث crash
نمی‌شود (همه خطاها به ساختار dict با success=False تبدیل می‌شوند).
"""

import json
import re
from collections.abc import Callable, Mapping
from typing import Optional

from config import FULL_WEEK, TODAY, WORKING_DAYS
from data import ClinicState

# ---------------------------------------------------------------------------
# نرمال‌سازی ورودی‌ها
# (مدل‌ها گاهی «سه شنبه»، «۱۵» یا «10 صبح» می‌فرستند؛ همه به قالب استاندارد می‌رسند)
# ---------------------------------------------------------------------------

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# کلیدها به شکل نرمال‌شده (نیم‌فاصله → فاصله) هستند
_DAY_ALIASES: dict[str, str] = {
    "شنبه": "شنبه",
    "یکشنبه": "یکشنبه",
    "یک شنبه": "یکشنبه",
    "دوشنبه": "دوشنبه",
    "دو شنبه": "دوشنبه",
    "سه شنبه": "سه‌شنبه",
    "سهشنبه": "سه‌شنبه",
    "چهارشنبه": "چهارشنبه",
    "چهار شنبه": "چهارشنبه",
    "پنجشنبه": "پنجشنبه",
    "پنج شنبه": "پنجشنبه",
    "جمعه": "جمعه",
    "امروز": "امروز",
    "فردا": "فردا",
    "پس فردا": "پس‌فردا",
}

_RELATIVE_DAYS: dict[str, int] = {"امروز": 0, "فردا": 1, "پس‌فردا": 2}

_PM_MARKERS = ("بعدازظهر", "بعد از ظهر", "بعدالظهر", "عصر", "ظهر", "شب", "pm")
_AM_MARKERS = ("صبح", "بامداد", "am")
_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{1,2}))?")


def _clean_text(value: object) -> str:
    """یکسان‌سازی نویسه‌های فارسی/عربی، ارقام و فاصله‌ها."""
    text = str(value).translate(_DIGIT_MAP)
    text = text.replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", text).strip()


def normalize_day(day: str) -> Optional[str]:
    """روز ورودی را به نام استاندارد کلینیک نگاشت می‌کند.

    «سه شنبه»، «سه‌شنبه»، ارقام فارسی و روزهای نسبی («امروز»، «فردا»،
    «پس فردا») پشتیبانی می‌شوند. اگر روز شناخته نشد None برمی‌گردد.
    """
    cleaned = _clean_text(day)
    if not cleaned:
        return None
    canonical = _DAY_ALIASES.get(cleaned)
    if canonical is None:
        return None
    if canonical in _RELATIVE_DAYS:
        today_index = FULL_WEEK.index(TODAY)
        offset = _RELATIVE_DAYS[canonical]
        return FULL_WEEK[(today_index + offset) % len(FULL_WEEK)]
    return canonical


def normalize_time(time: object) -> str:
    """زمان ورودی را به قالب ۲۴ ساعته «HH:MM» تبدیل می‌کند.

    «15»، «9:30»، «۱۰ صبح»، «3 عصر» و «ساعت 10 صبح» همگی پذیرفته می‌شوند.
    در بافت کلینیک، ساعت‌های ۸ و کمتر بدون صبح/عصر، عصر فرض می‌شوند
    («ساعت 3» یعنی 15:00). ورودی نامعتبر ValueError می‌دهد.
    """
    text = _clean_text(time)
    text = text.replace("٫", ":").replace("،", ":")
    match = _TIME_RE.search(text)
    if not match:
        raise ValueError(f"زمان «{time}» قابل درک نیست؛ مثال درست: 09:00 یا 15:00")

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)

    is_pm = any(marker in text for marker in _PM_MARKERS)
    is_am = any(marker in text for marker in _AM_MARKERS)
    if is_pm and hour < 12:
        hour += 12
    elif is_am and hour == 12:
        hour = 0
    elif not is_pm and not is_am and hour <= 8:
        hour += 12

    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        raise ValueError(f"زمان «{time}» خارج از محدوده مجاز است؛ مثال درست: 09:00 یا 15:00")
    return f"{hour:02d}:{minute:02d}"


# ---------------------------------------------------------------------------
# حافظه کلینیک (module-level؛ برای تست‌ها و دستور /reset بازسازی می‌شود)
# ---------------------------------------------------------------------------

clinic_state = ClinicState()


def reset_clinic_state(schedule: dict[str, list[str]] | None = None) -> ClinicState:
    """حافظه کلینیک را از نو می‌سازد و برمی‌گرداند."""
    global clinic_state
    clinic_state = ClinicState(schedule)
    return clinic_state


def tools_state_snapshot() -> list[dict]:
    """لیست نوبت‌های ثبت‌شدهٔ فعلی را به شکل dict برمی‌گرداند.

    همیشه از طریق همین تابع بخوانید تا بعد از reset هم مقدار تازه باشد
    (چون reset_clinic_state آبجکت را دوباره می‌سازد).
    """
    return [
        {
            "patient_name": appt.patient_name,
            "day": appt.day,
            "time": appt.time,
            "reason": appt.reason,
        }
        for appt in clinic_state.booked.values()
    ]


# ---------------------------------------------------------------------------
# Tool شماره ۱: دیدن زمان‌های آزاد
# ---------------------------------------------------------------------------


def get_available_slots(day: Optional[str] = None) -> dict:
    """Return the free (unbooked) appointment times of the doctor.

    ALWAYS use this tool to check the doctor's real schedule before talking
    about availability. Never guess whether a time is free; the schedule
    changes every time another patient books a slot.

    Args:
        day: Persian weekday name, exactly one of: "شنبه", "یکشنبه",
            "دوشنبه", "سه‌شنبه". Relative words "امروز" (today), "فردا"
            (tomorrow) and "پس فردا" are also accepted. Omit this parameter
            (or pass null) to get free slots of ALL working days at once.

    Returns:
        dict with keys: "success" (bool), "available_slots" (list of "HH:MM"
        strings for a single day, or a dict of {day: [times]} when all days
        are requested), "first_free" ({"day", "time"} or null: the earliest
        free slot), and "message" (short Persian summary).
        On failure "success" is false and "message" explains the problem.
    """
    if day is None or str(day).strip() == "":
        available = clinic_state.available_by_day()
        first_free = clinic_state.first_free()
        message = (
            "هیچ نوبت خالی وجود ندارد."
            if first_free is None
            else f"نزدیک‌ترین نوبت آزاد: {first_free['day']} ساعت {first_free['time']}"
        )
        return {
            "success": True,
            "available_slots": available,
            "first_free": first_free,
            "message": message,
        }

    resolved = normalize_day(day)
    if resolved is None:
        return {
            "success": False,
            "error": "UNKNOWN_DAY",
            "message": f"روز «{day}» شناخته نشد. روزهای کاری کلینیک: {'، '.join(WORKING_DAYS)}",
        }
    if resolved not in WORKING_DAYS:
        return {
            "success": False,
            "error": "CLINIC_CLOSED",
            "message": f"کلینیک در روز {resolved} تعطیل است. روزهای کاری: {'، '.join(WORKING_DAYS)}",
            "available_slots": [],
            "first_free": None,
        }

    times = clinic_state.available_times(resolved)
    first_free = {"day": resolved, "time": times[0]} if times else None
    message = (
        f"{resolved} در این ساعت‌ها آزاد است: {'، '.join(times)}"
        if times
        else f"{resolved} دیگر هیچ نوبت خالی ندارد."
    )
    return {
        "success": True,
        "day": resolved,
        "available_slots": times,
        "first_free": first_free,
        "message": message,
    }


# ---------------------------------------------------------------------------
# Tool شماره ۲: ثبت نوبت
# ---------------------------------------------------------------------------


def book_appointment(patient_name: str, day: str, time: str, reason: str = "ویزیت عمومی") -> dict:
    """Book a clinic appointment for a patient at an exact free slot.

    Call this tool ONLY AFTER "get_available_slots" showed the slot is free.
    Never tell the patient an appointment is confirmed unless this tool
    returns "success": true.

    If it fails, read "message": for SLOT_TAKEN and SLOT_NOT_FOUND the free
    alternatives are already included in "available_slots" and "first_free",
    so you can propose them (do not book an alternative yourself without the
    patient's approval; only when the patient let you pick freely, e.g. "just
    get me an appointment", you may book the first free slot directly).

    Args:
        patient_name: Full name of the patient in Persian, e.g. "پوریا". Required.
        day: Persian weekday name, exactly one of: "شنبه", "یکشنبه",
            "دوشنبه", "سه‌شنبه" ("امروز" and "فردا" are also accepted).
        time: Desired time in 24-hour "HH:MM" format, e.g. "09:00" or "15:00"
            (inputs like "15" or "10 صبح" are normalized automatically).
        reason: Short visit reason in Persian, e.g. "چکاپ". Optional.

    Returns:
        dict: on success {"success": true, "patient_name", "day", "time",
        "reason", "message"}; on failure {"success": false, "error",
        "message", ...} with error codes UNKNOWN_DAY, CLINIC_CLOSED,
        INVALID_TIME, SLOT_NOT_FOUND, SLOT_TAKEN or MISSING_NAME.
    """
    if not str(patient_name or "").strip():
        return {
            "success": False,
            "error": "MISSING_NAME",
            "message": "نام بیمار برای ثبت نوبت لازم است.",
        }

    resolved_day = normalize_day(day)
    if resolved_day is None:
        return {
            "success": False,
            "error": "UNKNOWN_DAY",
            "message": f"روز «{day}» شناخته نشد. روزهای کاری کلینیک: {'، '.join(WORKING_DAYS)}",
        }
    if resolved_day not in WORKING_DAYS:
        return {
            "success": False,
            "error": "CLINIC_CLOSED",
            "message": f"کلینیک در روز {resolved_day} تعطیل است. روزهای کاری: {'، '.join(WORKING_DAYS)}",
        }

    try:
        slot_time = normalize_time(time)
    except ValueError as exc:
        return {"success": False, "error": "INVALID_TIME", "message": str(exc)}

    if not clinic_state.has_slot(resolved_day, slot_time):
        return {
            "success": False,
            "error": "SLOT_NOT_FOUND",
            "message": f"{resolved_day} ساعت {slot_time} در برنامه کلینیک وجود ندارد.",
            "available_slots": clinic_state.available_times(resolved_day),
            "first_free": clinic_state.first_free(),
        }

    if clinic_state.slot_key(resolved_day, slot_time) in clinic_state.booked:
        return {
            "success": False,
            "error": "SLOT_TAKEN",
            "message": f"{resolved_day} ساعت {slot_time} قبلاً رزرو شده است.",
            "available_slots": clinic_state.available_times(resolved_day),
            "first_free": clinic_state.first_free(),
        }

    appointment = clinic_state.book(
        patient_name=str(patient_name).strip(),
        day=resolved_day,
        time=slot_time,
        reason=str(reason).strip() or "ویزیت عمومی",
    )
    return {
        "success": True,
        "patient_name": appointment.patient_name,
        "day": appointment.day,
        "time": appointment.time,
        "reason": appointment.reason,
        "message": "نوبت با موفقیت ثبت شد.",
    }


# ---------------------------------------------------------------------------
# اجرای امن Toolها (بدون eval)
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "get_available_slots": get_available_slots,
    "book_appointment": book_appointment,
}


def get_tool_callables() -> list[Callable[..., dict]]:
    """لیست توابع Tool برای پاس دادن به client.chat(tools=...)."""
    return list(TOOL_REGISTRY.values())


def execute_tool(name: str, arguments: Mapping | str | None) -> dict:
    """یک Tool را به‌صورت امن از روی TOOL_REGISTRY اجرا می‌کند.

    نام نامعتبر یا آرگومان‌های خراب، به‌جای exception، یک dict ساختاریافته
    با success=False برمی‌گرداند تا مدل بتواند خطا را بخواند و اصلاح کند.
    """
    if not isinstance(name, str) or name not in TOOL_REGISTRY:
        return {"success": False, "error": "UNKNOWN_TOOL", "message": f"Unknown tool: {name}"}

    try:
        if arguments is None:
            args: dict = {}
        elif isinstance(arguments, Mapping):
            args = dict(arguments)
        elif isinstance(arguments, str):
            args = json.loads(arguments) if arguments.strip() else {}
        else:
            args = dict(arguments)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return {"success": False, "error": "INVALID_ARGUMENTS", "message": f"Invalid arguments: {exc}"}

    try:
        return TOOL_REGISTRY[name](**args)
    except TypeError as exc:
        return {"success": False, "error": "INVALID_ARGUMENTS", "message": f"Invalid arguments: {exc}"}
    except Exception as exc:  # هیچ خطای Tool نباید Agent را بترکاند
        return {"success": False, "error": "TOOL_ERROR", "message": f"Tool failed: {exc}"}
