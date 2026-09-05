"""بررسی سریع سازگاری یک مدل Ollama با Tool Calling این پروژه.

این اسکریپت یک درخواست واقعی Tool Call به مدل می‌فرستد و گزارش می‌دهد که
آیا مدل tool_call صادر می‌کند یا فقط متن تولید می‌کند (یعنی نامناسب است).

اجرا:
    python check_model.py                    # آزمودن مدل پیش‌فرض config.py
    python check_model.py --model qwen3:4b   # آزمودن یک مدل خاص
    python check_model.py --list             # فقط نمایش مدل‌های نصب‌شده
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    from ollama import Client
except ImportError:
    print("کتابخانه ollama نصب نیست:  pip install -r requirements.txt")
    sys.exit(1)

from agent import DoctorAppointmentAgent
from config import MODEL, NUM_CTX, OLLAMA_HOST, TEMPERATURE
from tools import get_tool_callables

CHECK_SYSTEM = (
    "تو دستیار رزرو نوبت کلینیک هستی. برای دیدن زمان‌های آزاد پزشک حتماً از ابزار "
    "get_available_slots استفاده کن و خودت هیچ زمانی را حدس نزن."
)
CHECK_PROMPT = "اسمم پوریاست، برای چکاپ نوبت میخوام. اول زمان‌های آزاد پزشک را بررسی کن."


def list_models(client: Client) -> list[str]:
    return [m.get("model") for m in client.list()["models"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_model", description="تست سازگاری مدل Ollama با Tool Calling")
    parser.add_argument("--model", default=MODEL, help=f"نام مدل (پیش‌فرض: {MODEL})")
    parser.add_argument("--host", default=OLLAMA_HOST, help="آدرس سرور Ollama")
    parser.add_argument("--list", action="store_true", help="فقط نمایش مدل‌های نصب‌شده")
    args = parser.parse_args(argv)

    client = Client(host=args.host)
    try:
        models = list_models(client)
    except Exception as exc:
        print(f"⚠️  اتصال به Ollama برقرار نشد: {exc}")
        print("   ابتدا سرویس را اجرا کنید:  ollama serve")
        return 1

    if args.list:
        print("مدل‌های نصب‌شده:")
        for name in models:
            marker = "  ← پیش‌فرض پروژه" if name == args.model else ""
            print(f" - {name}{marker}")
        print("\nبرای بررسی قابلیت‌ها:  ollama show <model>   ← به دنبال «tools» در Capabilities بگردید")
        return 0

    if args.model not in models:
        print(f"⚠️  مدل «{args.model}» روی این سیستم نصب نیست. مدل‌های موجود:")
        for name in models:
            print(f" - {name}")
        print("\nیکی را با --model انتخاب کنید یا مدل را با «ollama pull» دانلود کنید.")
        return 1

    print(f"🔍 در حال آزمودن «{args.model}» با یک درخواست واقعی Tool Calling ...")
    started = time.time()
    try:
        response = client.chat(
            model=args.model,
            messages=[
                {"role": "system", "content": CHECK_SYSTEM},
                {"role": "user", "content": CHECK_PROMPT},
            ],
            tools=get_tool_callables(),
            options={"temperature": TEMPERATURE, "num_ctx": NUM_CTX},
        )
    except Exception as exc:
        print(f"⚠️  خطا در فراخوانی مدل: {exc}")
        return 1
    elapsed = time.time() - started

    message = DoctorAppointmentAgent._normalize_message(response["message"])
    tool_calls = message.get("tool_calls") or []
    content = DoctorAppointmentAgent.strip_think_tags(message.get("content") or "")

    if tool_calls:
        print(f"✅ مدل Tool Call صادر کرد ({elapsed:.1f} ثانیه) — سازگار است:")
        for call in tool_calls:
            name, arguments = DoctorAppointmentAgent._extract_call(call)
            rendered = ", ".join(f'{k}="{v}"' for k, v in arguments.items())
            print(f"   → {name}({rendered})")
        print("\nحالا می‌توانید اجرا کنید:  python main.py --model " + args.model)
        return 0

    print(f"❌ مدل بدون هیچ Tool Call فقط متن تولید کرد ({elapsed:.1f} ثانیه) — احتمالاً از Tool Calling پشتیبانی نمی‌کند.")
    if content:
        print(f"   متن پاسخ: {content[:200]}")
    print("   راه‌حل: «ollama show <model>» را اجرا کنید؛ در بخش Capabilities باید کلمه «tools» باشد.")
    print("   در غیر این صورت مدل دیگری انتخاب کنید (فهرست پیشنهادی: README بخش ۴).")
    return 2


if __name__ == "__main__":
    sys.exit(main())
