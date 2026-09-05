"""تست‌های لایه Tool و نرمال‌سازی (بدون نیاز به Ollama)."""

import pytest

from tools import (
    TOOL_REGISTRY,
    book_appointment,
    execute_tool,
    get_available_slots,
    normalize_day,
    normalize_time,
)


class TestNormalizeTime:
    def test_plain_24h(self):
        assert normalize_time("15:00") == "15:00"

    def test_hhmm_single_digit(self):
        assert normalize_time("9:30") == "09:30"

    def test_short_hour_becomes_slot(self):
        assert normalize_time("15") == "15:00"

    def test_morning_marker(self):
        assert normalize_time("10 صبح") == "10:00"

    def test_afternoon_word(self):
        assert normalize_time("3 عصر") == "15:00"

    def test_bare_small_hour_means_afternoon_in_clinic_context(self):
        assert normalize_time("3") == "15:00"

    def test_persian_digits(self):
        assert normalize_time("۹:۳۰") == "09:30"

    def test_out_of_range(self):
        with pytest.raises(ValueError):
            normalize_time("25:00")

    def test_garbage_without_number(self):
        with pytest.raises(ValueError):
            normalize_time("بعدازظهر")


class TestNormalizeDay:
    def test_canonical(self):
        assert normalize_day("شنبه") == "شنبه"

    def test_space_variant(self):
        assert normalize_day("سه شنبه") == "سه‌شنبه"

    def test_zwnj_variant(self):
        assert normalize_day("سه‌شنبه") == "سه‌شنبه"

    def test_relative_tomorrow(self):
        # امروز (شبیه‌سازی) شنبه است؛ فردا می‌شود یکشنبه
        assert normalize_day("فردا") == "یکشنبه"

    def test_unknown_day(self):
        assert normalize_day("یک روز") is None


class TestGetAvailableSlots:
    def test_all_days(self):
        result = get_available_slots()
        assert result["success"] is True
        assert result["available_slots"]["شنبه"] == ["09:00", "10:00", "11:00"]
        assert result["available_slots"]["دوشنبه"] == ["14:00", "15:00", "16:00"]
        assert result["first_free"] == {"day": "شنبه", "time": "09:00"}

    def test_single_day(self):
        result = get_available_slots("دوشنبه")
        assert result["success"] is True
        assert result["day"] == "دوشنبه"
        assert result["available_slots"] == ["14:00", "15:00", "16:00"]

    def test_relative_day_resolved(self):
        result = get_available_slots("فردا")
        assert result["success"] is True
        assert result["day"] == "یکشنبه"

    def test_unknown_day(self):
        result = get_available_slots("یک روز خاص")
        assert result["success"] is False
        assert result["error"] == "UNKNOWN_DAY"

    def test_closed_day(self):
        for closed in ("پنجشنبه", "جمعه"):
            result = get_available_slots(closed)
            assert result["success"] is False
            assert result["error"] == "CLINIC_CLOSED"

    def test_reflects_bookings(self):
        book_appointment("پوریا", "شنبه", "09:00", "چکاپ")
        result = get_available_slots("شنبه")
        assert "09:00" not in result["available_slots"]
        assert result["available_slots"] == ["10:00", "11:00"]

    def test_empty_day_after_full_booking(self):
        for time in ("09:00", "10:00", "11:00"):
            book_appointment("پرکننده", "شنبه", time, "ویزیت عمومی")
        result = get_available_slots("شنبه")
        assert result["available_slots"] == []
        assert result["first_free"] is None


class TestBookAppointment:
    def test_success_result_shape(self):
        result = book_appointment("پوریا", "شنبه", "09:00", "چکاپ")
        assert result["success"] is True
        assert result["patient_name"] == "پوریا"
        assert result["day"] == "شنبه"
        assert result["time"] == "09:00"
        assert result["reason"] == "چکاپ"

    def test_double_booking_fails_with_alternatives(self):
        assert book_appointment("پوریا", "شنبه", "09:00", "چکاپ")["success"] is True
        second = book_appointment("علی", "شنبه", "9", "سرماخوردگی")  # «9» → 09:00
        assert second["success"] is False
        assert second["error"] == "SLOT_TAKEN"
        assert "11:00" in second["available_slots"]

    def test_slot_not_in_schedule(self):
        result = book_appointment("پوریا", "دوشنبه", "10:00", "چکاپ")
        assert result["success"] is False
        assert result["error"] == "SLOT_NOT_FOUND"
        assert result["available_slots"] == ["14:00", "15:00", "16:00"]

    def test_time_normalization_on_booking(self):
        result = book_appointment("پوریا", "دوشنبه", "3 عصر", "چکاپ")
        assert result["success"] is True
        assert result["time"] == "15:00"

    def test_missing_name(self):
        result = book_appointment("", "شنبه", "09:00", "چکاپ")
        assert result["success"] is False
        assert result["error"] == "MISSING_NAME"

    def test_invalid_time(self):
        result = book_appointment("پوریا", "شنبه", "25:99", "چکاپ")
        assert result["success"] is False
        assert result["error"] == "INVALID_TIME"

    def test_closed_day_booking(self):
        result = book_appointment("پوریا", "جمعه", "09:00", "چکاپ")
        assert result["success"] is False
        assert result["error"] == "CLINIC_CLOSED"

    def test_reason_default(self):
        result = book_appointment("پوریا", "شنبه", "10:00", "")
        assert result["success"] is True
        assert result["reason"] == "ویزیت عمومی"


class TestExecuteTool:
    def test_registry_has_exactly_two_tools(self):
        assert set(TOOL_REGISTRY) == {"get_available_slots", "book_appointment"}

    def test_unknown_tool_message(self):
        result = execute_tool("send_email", {})
        assert result["success"] is False
        assert result["message"] == "Unknown tool: send_email"

    def test_invalid_arguments_message(self):
        result = execute_tool("book_appointment", {"patient_name": "پوریا"})  # day و time جا افتاده
        assert result["success"] is False
        assert result["error"] == "INVALID_ARGUMENTS"
        assert result["message"].startswith("Invalid arguments:")

    def test_arguments_as_json_string(self):
        result = execute_tool("get_available_slots", '{"day": "دوشنبه"}')
        assert result["success"] is True
        assert result["day"] == "دوشنبه"

    def test_routes_to_tool(self):
        result = execute_tool("get_available_slots", {"day": "دوشنبه"})
        assert result["success"] is True
        assert result["available_slots"] == ["14:00", "15:00", "16:00"]
