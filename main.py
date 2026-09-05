"""نقطه ورود برنامه: چت تعاملی با Agent رزرو نوبت پزشک.

اجرا:
    python main.py                     # اتصال به Ollama و چت تعاملی
    python main.py --model llama3.1:8b # اجرا با مدل دیگر
    python main.py --demo              # سناریوهای نمونه با شبیه‌ساز مدل (بدون نیاز به Ollama)
    python main.py --doctor            # عیب‌یابی اتصال/مدل‌ها با گزارش فارسی
    python web_app.py                  # رابط وب حرفه‌ای روی سیستم خودتان (بدون CORS)
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from agent import DoctorAppointmentAgent
from config import DOCTOR_NAME, DOCTOR_SPECIALTY, MODEL, OLLAMA_HOST, TODAY, WORKING_DAYS
from diagnostics import doctor_report, resolve_model
from tools import reset_clinic_state


def _enable_utf8_stdio() -> None:
    """روی ویندوز، چاپ فارسی/ایموجی بدون UTF-8 خطا می‌دهد؛ آن را تضمین می‌کند."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def banner(model: str) -> str:
    return f"""
────────────────────────────────────────────────────────
 🩺  Agent رزرو نوبت {DOCTOR_NAME} ({DOCTOR_SPECIALTY})
     مدل: {model}  |  سرور: {OLLAMA_HOST}
     روزهای کاری: {'، '.join(WORKING_DAYS)}  |  امروز (شبیه‌سازی): {TODAY}
────────────────────────────────────────────────────────
 دستورها:  /reset = پاک‌سازی گفتگو و نوبت‌ها  |  /exit = خروج
 نمونه:   «اسمم پوریاست، برای چکاپ نوبت میخوام»
────────────────────────────────────────────────────────"""


def _looks_like_connection_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return "connect" in name or "connect" in text or "connection" in text


def check_server(agent: DoctorAppointmentAgent) -> bool:
    """قبل از شروع چت، دسترسی به سرویس Ollama و وجود مدل را می‌سنجد."""
    try:
        agent.client.list()
        return True
    except Exception as exc:
        print(f"⚠️  اتصال به Ollama برقرار نشد: {exc}")
        print("   ۱) مطمئن شوید سرویس در حال اجراست:  ollama serve")
        print("   ۲) عیب‌یابی کامل با یک دستور:  python main.py --doctor")
        print(f"   ۳) مدل را دانلود کنید:  ollama pull {agent.model}")
        print("   ۴) بدون GPU/مدل هم می‌توانید جریان Agent را ببینید:  python main.py --demo")
        return False


def run_chat(agent: DoctorAppointmentAgent) -> None:
    """حلقه چت تعاملی با کاربر در ترمینال."""
    print(banner(agent.model))
    while True:
        try:
            user_input = input("\n👤 شما> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 خداحافظ!")
            return

        if not user_input:
            continue
        if user_input.lower() in ("/exit", "/quit", "/خروج", "exit", "quit"):
            print("👋 خداحافظ!")
            return
        if user_input.lower() in ("/reset", "/ریست"):
            agent.reset()
            reset_clinic_state()
            print("♻️  گفتگو و نوبت‌های کلینیک ریست شد.")
            continue

        try:
            agent.chat(user_input)
        except KeyboardInterrupt:
            print("\n(درخواست لغو شد)")
        except Exception as exc:  # CLI نباید با یک خطا بترکد
            print(f"\n⚠️  خطا: {exc}")
            if _looks_like_connection_error(exc):
                print("   سرویس Ollama در دسترس نیست؛ «ollama serve» را اجرا کنید.")


# ---------------------------------------------------------------------------
# حالت دمو: اجرای سناریوهای آماده بدون نیاز به Ollama
# ---------------------------------------------------------------------------


class DemoModelClient:
    """شبیه‌ساز کوچک پاسخ‌های مدل برای حالت ``--demo``.

    دقیقاً مثل یک مدل واقعی در حلقه Tool Calling شرکت می‌کند: گاهی
    tool_call می‌دهد و گاهی پاسخ نهایی. تنها تفاوت این است که تصمیم‌هایش
    از پیش نوشته شده‌اند؛ اجرای Toolها و حافظه کلینیک کاملاً واقعی است.
    """

    def __init__(self, plans: list[tuple[Callable[[str], bool], list[tuple]]]) -> None:
        self.plans = plans
        self._steps: list[tuple] = []
        self._cursor = 0

    def chat(self, model: str, messages: list, tools=None, options=None, **kwargs):
        last = messages[-1]
        if last["role"] == "user":
            self._steps = next(
                (steps for predicate, steps in self.plans if predicate(last["content"])),
                [
                    ("tool", "get_available_slots", {}),
                    ("final", "برای ادامه لطفاً درخواستتان را کامل‌تر بگویید."),
                ],
            )
            self._cursor = 0
        step = self._steps[self._cursor]
        self._cursor += 1
        if step[0] == "tool":
            _, name, arguments = step
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
                }
            }
        return {"message": {"role": "assistant", "content": step[1]}}


def _demo_plans() -> list[tuple[Callable[[str], bool], list[tuple]]]:
    def has(*needles: str) -> Callable[[str], bool]:
        return lambda text: any(needle in text for needle in needles)

    def has_all(*needles: str) -> Callable[[str], bool]:
        return lambda text: all(needle in text for needle in needles)

    # ترتیب مهم است: الگوی خاص‌تر باید اول بررسی شود
    return [
        (
            has_all("پوریا", "چکاپ"),
            [
                ("tool", "get_available_slots", {}),
                ("tool", "book_appointment", {"patient_name": "پوریا", "day": "شنبه", "time": "09:00", "reason": "چکاپ"}),
                ("final", "نوبت چکاپ شما برای شنبه ساعت 09:00 ثبت شد، پوریا عزیز."),
            ],
        ),
        (
            has_all("دوشنبه", "15"),
            [
                ("tool", "get_available_slots", {"day": "دوشنبه"}),
                ("tool", "book_appointment", {"patient_name": "پوریا", "day": "دوشنبه", "time": "15:00", "reason": "ویزیت عمومی"}),
                ("final", "نوبت شما برای دوشنبه ساعت 15:00 ثبت شد."),
            ],
        ),
        (
            has("دوشنبه"),
            [
                ("tool", "get_available_slots", {"day": "دوشنبه"}),
                ("tool", "book_appointment", {"patient_name": "پوریا", "day": "دوشنبه", "time": "14:00", "reason": "ویزیت عمومی"}),
                ("final", "نوبت شما برای دوشنبه ساعت 14:00 (اولین زمان آزادِ همان روز) ثبت شد."),
            ],
        ),
        (
            has("فردا"),
            [
                ("tool", "get_available_slots", {"day": "فردا"}),
                ("final", "فردا (یکشنبه) ساعت 10:00 پذیرش نداریم؛ نزدیک‌ترین زمان‌های آزاد 09:30 و 10:30 است. کدام را برایتان رزرو کنم؟"),
            ],
        ),
        (
            has("10 صبح", "ساعت 10"),
            [
                ("tool", "get_available_slots", {}),
                ("final", "بله، شنبه ساعت 10:00 آزاد است. لطفاً نام خود را بگویید تا نوبت را ثبت کنم."),
            ],
        ),
        (
            has("اسمم"),
            [
                ("tool", "get_available_slots", {}),
                ("tool", "book_appointment", {"patient_name": "پوریا", "day": "شنبه", "time": "10:00", "reason": "ویزیت عمومی"}),
                ("final", "نوبت شما برای شنبه ساعت 10:00 ثبت شد، پوریا عزیز."),
            ],
        ),
    ]


DEMO_TURNS: list[list[str]] = [
    ["اسمم پوریاست، برای چکاپ نوبت میخوام"],
    ["برای دوشنبه نوبت میخوام"],
    ["دوشنبه ساعت 15 نوبت میخوام"],
    ["ساعت 10 صبح نوبت میخوام", "اسمم پوریاست"],
    ["برای فردا ساعت 10 صبح وقت دارید؟"],
]


def run_demo() -> None:
    """سناریوهای نمونه را با شبیه‌ساز مدل اجرا می‌کند (بدون Ollama)."""
    print("🎬 حالت دمو: مدل با یک شبیه‌ساز جایگزین شده (بدون نیاز به Ollama).")
    print("   حلقه Tool Calling، اجرای امن Toolها و حافظه کلینیک کاملاً واقعی‌اند.")
    for turns in DEMO_TURNS:
        reset_clinic_state()
        agent = DoctorAppointmentAgent(client=DemoModelClient(_demo_plans()), verbose=True)
        print("\n" + "─" * 64)
        for turn in turns:
            agent.chat(turn)


# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="doctor-agent",
        description="Agent رزرو نوبت پزشک با Ollama Tool Calling",
    )
    parser.add_argument("--model", default=MODEL, help=f"نام مدل Ollama (پیش‌فرض: {MODEL})")
    parser.add_argument("--host", default=OLLAMA_HOST, help="آدرس سرور Ollama")
    parser.add_argument("--demo", action="store_true", help="اجرای سناریوهای نمونه با شبیه‌ساز مدل، بدون نیاز به Ollama")
    parser.add_argument("--doctor", action="store_true", help="عیب‌یابی اتصال Ollama و انتخاب خودکار مدل مناسب")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _enable_utf8_stdio()
    args = parse_args(argv)
    if args.demo:
        run_demo()
        return 0

    if args.doctor:
        _enable_utf8_stdio()
        print(doctor_report(args.host, args.model))
        return 0

    # انتخاب خودکار مدل: اگر تگ دقیق نصب نبود، نزدیک‌ترین مدل مناسب پیدا می‌شود
    model, notice = resolve_model(args.host, args.model)
    if notice:
        print(f"ℹ️  {notice}")

    try:
        agent = DoctorAppointmentAgent(model=model, host=args.host)
    except RuntimeError as exc:
        print(f"⚠️  {exc}")
        return 1

    if not check_server(agent):
        return 1
    run_chat(agent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
