"""تست سناریوهای Agent با یک کلاینت مدل تقلبی (بدون نیاز به Ollama).

کلاینت تقلبی دقیقاً مثل یک مدل واقعی در حلقه Tool Calling شرکت می‌کند:
گاهی tool_call می‌دهد و گاهی پاسخ متنی نهایی. اجرای Toolها، نتیجه‌ها و
حافظه کلینیک کاملاً واقعی‌اند؛ فقط «تصمیم‌های مدل» اسکریپت‌شده‌اند.
"""

import json
from collections.abc import Callable

import pytest

import tools
from agent import DoctorAppointmentAgent, strip_think_tags
from data import DEFAULT_SCHEDULE
from tools import book_appointment, reset_clinic_state


class ScriptedModelClient:
    """جایگزین ollama.Client در تست‌ها؛ سناریوها را به ترتیب اجرا می‌کند."""

    def __init__(self) -> None:
        self.plans: list[tuple[Callable[[str], bool], list[tuple]]] = []
        self.calls: list[dict] = []
        self.loop_forever = False
        self._steps: list[tuple] = []
        self._cursor = 0

    def add_plan(self, predicate: Callable[[str], bool], steps: list[tuple]) -> "ScriptedModelClient":
        self.plans.append((predicate, steps))
        return self

    def chat(self, model: str, messages: list, tools=None, options=None, **kwargs):
        self.calls.append(
            {"model": model, "messages": [dict(m) for m in messages], "tools": tools, "options": options}
        )
        if self.loop_forever:
            return self._tool_response("get_available_slots", {})
        last = messages[-1]
        if last["role"] == "user":
            self._steps = next(
                (steps for predicate, steps in self.plans if predicate(last["content"])),
                [("final", "سناریویی برای این پیام تعریف نشده است.")],
            )
            self._cursor = 0
        if self._cursor >= len(self._steps):
            return {"message": {"role": "assistant", "content": "سناریو تمام شد."}}
        step = self._steps[self._cursor]
        self._cursor += 1
        if step[0] == "tool":
            _, name, arguments = step
            return self._tool_response(name, arguments)
        return {"message": {"role": "assistant", "content": step[1]}}

    @staticmethod
    def _tool_response(name: str, arguments: dict) -> dict:
        return {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
            }
        }


def user_has(text: str) -> Callable[[str], bool]:
    return lambda message: text in message


def state() -> tools.ClinicState:
    """حافظه جاری کلینیک؛ همیشه از طریق ماژول خوانده می‌شود تا بعد از reset تازه باشد."""
    return tools.clinic_state


def tool_payloads(agent: DoctorAppointmentAgent) -> list[dict]:
    return [
        json.loads(message["content"])
        for message in agent.messages
        if message["role"] == "tool"
    ]


@pytest.fixture()
def client():
    return ScriptedModelClient()


@pytest.fixture()
def agent(client):
    return DoctorAppointmentAgent(client=client, verbose=False)


# ---------------------------------------------------------------------------
# Test 1: «اسمم پوریاست، برای چکاپ نوبت میخوام» → بررسی Slotها، اولین زمان آزاد، رزرو
# ---------------------------------------------------------------------------


def test_test1_books_first_free_slot(client, agent):
    client.add_plan(
        user_has("پوریا"),
        [
            ("tool", "get_available_slots", {}),
            ("tool", "book_appointment", {"patient_name": "پوریا", "day": "شنبه", "time": "09:00", "reason": "چکاپ"}),
            ("final", "نوبت شما برای شنبه ساعت 09:00 با موفقیت ثبت شد."),
        ],
    )
    answer = agent.chat("اسمم پوریاست، برای چکاپ نوبت میخوام")

    assert "شنبه" in answer and "09:00" in answer
    assert list(state().booked) == ["شنبه|09:00"]
    assert state().booked["شنبه|09:00"].patient_name == "پوریا"

    # مدل ابتدا Slotها را گرفته و سپس نوبت را رزرو کرده است
    payloads = tool_payloads(agent)
    assert len(payloads) == 2
    assert payloads[0]["tool"] == "get_available_slots"
    assert payloads[0]["output"]["first_free"] == {"day": "شنبه", "time": "09:00"}
    assert payloads[1]["output"]["success"] is True


# ---------------------------------------------------------------------------
# Test 2: «برای دوشنبه نوبت میخوام» → فقط Slotهای دوشنبه بررسی شوند
# ---------------------------------------------------------------------------


def test_test2_only_requested_day_is_checked(client, agent):
    client.add_plan(
        user_has("دوشنبه"),
        [
            ("tool", "get_available_slots", {"day": "دوشنبه"}),
            ("tool", "book_appointment", {"patient_name": "پوریا", "day": "دوشنبه", "time": "14:00", "reason": "ویزیت عمومی"}),
            ("final", "نوبت شما برای دوشنبه ساعت 14:00 ثبت شد."),
        ],
    )
    agent.chat("برای دوشنبه نوبت میخوام")

    # فراخوانی Tool اول باید فقط روز دوشنبه را خواسته باشد
    slots_call = next(m for m in client.calls[1]["messages"] if m.get("tool_calls"))
    assert slots_call["tool_calls"][0]["function"]["arguments"] == {"day": "دوشنبه"}

    booked_days = {appt.day for appt in state().booked.values()}
    assert booked_days == {"دوشنبه"}


# ---------------------------------------------------------------------------
# Test 3: «دوشنبه ساعت 15 نوبت میخوام» → رزرو 15:00 یا پیشنهاد جایگزین
# ---------------------------------------------------------------------------


def test_test3_books_requested_time_when_free(client, agent):
    client.add_plan(
        user_has("15"),
        [
            ("tool", "get_available_slots", {"day": "دوشنبه"}),
            ("tool", "book_appointment", {"patient_name": "پوریا", "day": "دوشنبه", "time": "15:00", "reason": "ویزیت عمومی"}),
            ("final", "نوبت برای دوشنبه ساعت 15:00 ثبت شد."),
        ],
    )
    answer = agent.chat("دوشنبه ساعت 15 نوبت میخوام")

    assert "15:00" in answer
    assert state().slot_key("دوشنبه", "15:00") in state().booked


def test_test3_suggests_alternative_when_taken(client, agent):
    book_appointment("بیمار دیگر", "دوشنبه", "15:00", "ویزیت عمومی")
    client.add_plan(
        user_has("15"),
        [
            ("tool", "get_available_slots", {"day": "دوشنبه"}),
            ("final", "دوشنبه ساعت 15:00 پر شده است؛ نزدیک‌ترین زمان‌های آزاد: 14:00 و 16:00. کدام را رزرو کنم؟"),
        ],
    )
    answer = agent.chat("دوشنبه ساعت 15 نوبت میخوام")

    assert "16:00" in answer
    # بدون تأیید کاربر، زمان دیگری رزرو نشده است
    assert list(state().booked) == ["دوشنبه|15:00"]


# ---------------------------------------------------------------------------
# Test 4: «ساعت 10 صبح نوبت میخوام» → بدون نام؛ اول پرسیدن نام، بعد رزرو
# ---------------------------------------------------------------------------


def test_test4_morning_time_with_name_question(client, agent):
    client.add_plan(
        user_has("10 صبح"),
        [
            ("tool", "get_available_slots", {}),
            ("final", "بله، شنبه ساعت 10:00 آزاد است. لطفاً نام خود را بگویید تا نوبت را ثبت کنم."),
        ],
    )
    client.add_plan(
        user_has("اسمم"),
        [
            ("tool", "get_available_slots", {}),
            ("tool", "book_appointment", {"patient_name": "پوریا", "day": "شنبه", "time": "10:00", "reason": "ویزیت عمومی"}),
            ("final", "نوبت شما برای شنبه ساعت 10:00 ثبت شد."),
        ],
    )
    first = agent.chat("ساعت 10 صبح نوبت میخوام")
    assert "نام" in first
    assert not state().booked  # هنوز چیزی رزرو نشده

    second = agent.chat("اسمم پوریاست")
    assert "شنبه" in second
    assert state().slot_key("شنبه", "10:00") in state().booked


def test_test4_suggests_nearby_when_exact_time_taken(client, agent):
    book_appointment("بیمار دیگر", "شنبه", "10:00", "ویزیت عمومی")
    client.add_plan(
        user_has("10 صبح"),
        [
            ("tool", "get_available_slots", {}),
            ("final", "ساعت 10:00 شنبه پر شده است؛ نزدیک‌ترین زمان آزاد شنبه 11:00 است. رزرو کنم؟"),
        ],
    )
    answer = agent.chat("ساعت 10 صبح نوبت میخوام")

    assert "11:00" in answer
    assert len(state().booked) == 1  # فقط رزرو اولیه


# ---------------------------------------------------------------------------
# Test 5: پر بودن تمام Slotها → پیام «هیچ نوبت خالی وجود ندارد»
# ---------------------------------------------------------------------------


def test_test5_no_slots_left(client, agent):
    # همه Slotهای برنامه را پر می‌کنیم
    for day, times in DEFAULT_SCHEDULE.items():
        for time in times:
            assert book_appointment("پرکننده", day, time, "ویزیت عمومی")["success"] is True

    client.add_plan(
        user_has(""),
        [
            ("tool", "get_available_slots", {}),
            ("final", "متأسفانه در حال حاضر هیچ نوبت خالی وجود ندارد."),
        ],
    )
    answer = agent.chat("یه نوبت میخوام")

    assert "هیچ نوبت خالی" in answer
    payload = tool_payloads(agent)[0]
    assert all(not times for times in payload["output"]["available_slots"].values())
    assert payload["output"]["first_free"] is None


# ---------------------------------------------------------------------------
# مدیریت خطا: Tool نامعتبر، arguments ناقص، حلقه بی‌نهایت
# ---------------------------------------------------------------------------


def test_unknown_tool_is_reported_back_to_model(client, agent):
    client.add_plan(
        user_has("پوریا"),
        [
            ("tool", "send_sms", {"to": "پوریا"}),
            ("final", "ابزار پیامک ندارم؛ اما می‌توانم نوبت را ثبت کنم."),
        ],
    )
    agent.chat("اسمم پوریاست، نوبت میخوام")

    payload = tool_payloads(agent)[0]
    assert payload["output"]["success"] is False
    assert payload["output"]["message"] == "Unknown tool: send_sms"


def test_invalid_arguments_are_reported_back_to_model(client, agent):
    client.add_plan(
        user_has("پوریا"),
        [
            ("tool", "book_appointment", {"patient_name": "پوریا"}),  # day و time جا افتاده
            ("final", "برای ثبت نوبت به روز و ساعت نیاز دارم."),
        ],
    )
    agent.chat("اسمم پوریاست، نوبت میخوام")

    payload = tool_payloads(agent)[0]
    assert payload["output"]["success"] is False
    assert payload["output"]["error"] == "INVALID_ARGUMENTS"
    assert payload["output"]["message"].startswith("Invalid arguments:")


def test_iteration_guard_stops_infinite_tool_loop(client, agent):
    client.loop_forever = True
    agent.max_iterations = 2
    answer = agent.chat("یه نوبت میخوام")

    # دو دور با Tool + یک فراخوانی نهایی بدون Tool
    assert len(client.calls) == 3
    assert "tools" not in client.calls[2] or client.calls[2]["tools"] is None
    assert "متأسفانه" in answer


# ---------------------------------------------------------------------------
# تنظیمات چرخه مدل: temperature=0، معرفی Toolها، پاک‌سازی تگ think
# ---------------------------------------------------------------------------


def test_model_options_and_tools_wiring(client, agent):
    client.add_plan(user_has("سلام"), [("final", "سلام! چطور می‌توانم کمک کنم؟")])
    agent.chat("سلام")

    first_call = client.calls[0]
    assert first_call["options"]["temperature"] == 0
    assert {tool.__name__ for tool in first_call["tools"]} == {
        "get_available_slots",
        "book_appointment",
    }
    assert first_call["messages"][0]["role"] == "system"
    assert first_call["model"] == agent.model


def test_final_answer_strips_think_tags(client, agent):
    client.add_plan(
        user_has("سلام"),
        [("final", "<think>بگذار بررسی کنم</think>سلام! چه کمکی از من برمی‌آید؟")],
    )
    assert agent.chat("سلام") == "سلام! چه کمکی از من برمی‌آید؟"


def test_reset_clears_history(client, agent):
    client.add_plan(user_has("سلام"), [("final", "سلام!")])
    agent.chat("سلام")
    assert len(agent.messages) > 2

    agent.reset()
    assert agent.messages == [{"role": "system", "content": agent.messages[0]["content"]}]
    assert len(agent.messages) == 1


def test_strip_think_tags_helper():
    assert strip_think_tags("<think>x</think>پاسخ") == "پاسخ"
    assert strip_think_tags("پاسخ تمیز") == "پاسخ تمیز"
    assert strip_think_tags("") == ""
