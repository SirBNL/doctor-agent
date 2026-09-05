"""Agent رزرو نوبت پزشک با Ollama Tool Calling.

کلاس ``DoctorAppointmentAgent`` گفتگو را مدیریت می‌کند:

    1) پیام system را تنظیم می‌کند و تاریخچه را نگه می‌دارد.
    2) Toolها را به Ollama معرفی می‌کند.
    3) اگر مدل tool_call داد: نام و arguments را استخراج، Tool را به‌صورت
       امن اجرا و نتیجه را با role="tool" به تاریخچه اضافه می‌کند و دوباره
       مدل را صدا می‌زند.
    4) وقتی مدل دیگر tool_call نداشت، پاسخ متنی نهایی را برمی‌گرداند.
    5) با MAX_TOOL_ITERATIONS از حلقه بی‌نهایت جلوگیری می‌شود.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

try:  # کتابخانه ollama فقط برای اتصال واقعی لازم است؛ تست‌ها با کلاینت تقلبی کار می‌کنند
    from ollama import Client
except ImportError:  # pragma: no cover
    Client = None  # type: ignore[assignment]

from config import MAX_TOOL_ITERATIONS, MODEL, NUM_CTX, OLLAMA_HOST, SYSTEM_PROMPT, TEMPERATURE
from tools import execute_tool, get_tool_callables

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think_tags(text: str) -> str:
    """برخی مدل‌ها (مثل qwen3) در متن پاسخ، تگ <think> می‌گذارند؛ حذفش می‌کند."""
    return _THINK_RE.sub("", text or "").strip()


def translate_ollama_error(exc: Exception) -> str:
    """خطاهای خام کتابخانه/سرور Ollama را به پیام قابل‌فهم فارسی تبدیل می‌کند."""
    text = f"{type(exc).__name__}: {exc}"
    low = text.lower()
    if "not found" in low or "404" in low:
        return (
            "مدل انتخابی روی Ollama نصب نیست."
            " با «python main.py --doctor» لیست مدل‌های نصب‌شده و مدل پیشنهادی را ببینید"
            " یا مدل را دانلود کنید: ollama pull <model>"
        )
    if "timed out" in low or "timeout" in low or "readerror" in low:
        return (
            "پاسخی از Ollama دریافت نشد (timeout)."
            " احتمالاً مدل در حال بارگذاری است یا دستگاه مشغول است؛ کمی بعد دوباره تلاش کنید"
            " یا یک مدل سبک‌تر انتخاب کنید."
        )
    if (
        "connect" in low
        or "connection" in low
        or "refused" in low
        or "connectionerror" in low
    ):
        return (
            "اتصال به سرویس Ollama برقرار نشد."
            " ۱) سرویس را اجرا کنید: ollama serve"
            " (در ویندوز آیکن Ollama کنار ساعت باید فعال باشد)."
            " ۲) اگر پورت فرق دارد با --host بدهید. ۳) عیب‌یابی کامل: python main.py --doctor"
        )
    if "tool" in low and ("does not support" in low or "not supported" in low or "400" in low):
        return (
            "این مدل از Tool Calling پشتیبانی نمی‌کند."
            " با «python main.py --doctor» یک مدل سازگار انتخاب کنید"
            " (مثل qwen3-coder یا qwen2.5)."
        )
    return f"خطای غیرمنتظره در ارتباط با Ollama: {text}"



class DoctorAppointmentAgent:
    """Agent رزرو نوبت؛ مدل زبانی را با Toolهای کلینیک در حلقه می‌چرخاند."""

    def __init__(
        self,
        model: str = MODEL,
        host: str = OLLAMA_HOST,
        client: Any | None = None,
        verbose: bool = True,
    ) -> None:
        if client is None:
            if Client is None:
                raise RuntimeError(
                    "کتابخانه ollama نصب نیست. آن را با «pip install -r requirements.txt» نصب کنید."
                )
            client = Client(host=host)
        self.model = model
        self.client = client
        self.verbose = verbose
        self.max_iterations = MAX_TOOL_ITERATIONS
        self.tools = get_tool_callables()
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        # رد اجرای آخرین نوبت (برای نمایش در رابط وب): {name, arguments, result, duration_ms}
        self.last_trace: list[dict] = []

    # ------------------------------ API اصلی ------------------------------

    def reset(self) -> None:
        """تاریخچه گفتگو را پاک می‌کند (حافظه کلینیک جداگانه در tools.py ریست می‌شود)."""
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def chat(self, user_message: str) -> str:
        """یک پیام کاربر را پردازش و پاسخ نهایی مدل را برمی‌گرداند."""
        user_message = user_message.strip()
        self._log("👤 User:", user_message)
        self.messages.append({"role": "user", "content": user_message})
        self.last_trace = []

        options = {"temperature": TEMPERATURE, "num_ctx": NUM_CTX}
        for _ in range(self.max_iterations):
            response = self._call_model(self.messages, tools=self.tools, options=options)
            assistant = self._normalize_message(response["message"])
            self.messages.append(assistant)

            tool_calls = assistant.get("tool_calls") or []
            if not tool_calls:
                answer = strip_think_tags(assistant.get("content") or "")
                answer = answer or "متأسفانه نتوانستم پاسخ مناسبی تولید کنم؛ لطفاً دوباره تلاش کنید."
                self._log("🤖 Assistant:", answer)
                return answer

            for call in tool_calls:
                name, arguments = self._extract_call(call)
                self._log_tool_call(name, arguments)
                started = time.perf_counter()
                result = execute_tool(name, arguments)
                duration_ms = round((time.perf_counter() - started) * 1000, 1)
                self.last_trace.append(
                    {"name": name, "arguments": arguments, "result": result, "duration_ms": duration_ms}
                )
                self._log_tool_result(result)
                # نتیجه Tool با role="tool" به تاریخچه برمی‌گردد تا مدل آن را ببیند
                self.messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(
                            {"tool": name, "output": result}, ensure_ascii=False
                        ),
                    }
                )

        # محافظ حلقه بی‌نهایت: یک بار بدون Tool پاسخ متنی می‌گیریم
        self._log("⚠️", f"حداکثر تعداد فراخوانی Tool ({self.max_iterations}) پر شد؛ پاسخ نهایی بدون Tool گرفته می‌شود.")
        response = self._call_model(self.messages, options=options)
        answer = strip_think_tags(self._content_of(response["message"]))
        answer = answer or "متأسفانه نتوانستم درخواست شما را کامل کنم؛ لطفاً درخواست را ساده‌تر بیان کنید."
        self._log("🤖 Assistant:", answer)
        return answer

    def _call_model(self, messages: list[dict], tools: list | None = None, options: dict | None = None) -> dict:
        """فراخوانی مدل با ترجمه خودکار خطاها به پیام فارسی قابل‌فهم."""
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "options": options or {}}
        if tools is not None:
            kwargs["tools"] = tools
        try:
            return self.client.chat(**kwargs)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            raise RuntimeError(translate_ollama_error(exc)) from exc

    # --------------------------- نرمال‌سازی پاسخ ---------------------------

    @staticmethod
    def _normalize_message(message: Any) -> dict:
        """پیام مدل (dict یا آبجکت pydantic کتابخانه ollama) را به dict ساده تبدیل می‌کند."""
        if not isinstance(message, dict):
            message = message.model_dump(exclude_none=True)
        normalized: dict = {"role": "assistant", "content": message.get("content") or ""}
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            normalized["tool_calls"] = [
                DoctorAppointmentAgent._normalize_tool_call(call) for call in tool_calls
            ]
        return normalized

    @staticmethod
    def _normalize_tool_call(call: Any) -> dict:
        """tool_call را به {"function": {"name", "arguments"(dict)}} پایدار تبدیل می‌کند."""
        function = call.get("function", {}) if isinstance(call, dict) else call.function
        if isinstance(function, dict):
            name = function.get("name") or ""
            arguments = function.get("arguments") or {}
        else:
            name = getattr(function, "name", "") or ""
            arguments = getattr(function, "arguments", None) or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                arguments = {"_invalid": arguments}
        if not isinstance(arguments, dict):
            arguments = {}
        return {"function": {"name": str(name), "arguments": dict(arguments)}}

    @staticmethod
    def _extract_call(call: dict) -> tuple[str, dict]:
        """نام Tool و arguments را از یک tool_call نرمال‌شده برمی‌دارد."""
        function = call.get("function", {})
        return function.get("name", ""), function.get("arguments") or {}

    @staticmethod
    def _content_of(message: Any) -> str:
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
        return content or ""

    # ------------------------------- لاگ‌ها -------------------------------

    def _log(self, title: str, body: str) -> None:
        if self.verbose:
            print(f"\n{title}\n{body}")

    def _log_tool_call(self, name: str, arguments: dict) -> None:
        if not self.verbose:
            return
        if not arguments:
            rendered = f"{name}()"
        elif len(arguments) > 2:
            pairs = ",\n".join(f'    {key}="{value}"' for key, value in arguments.items())
            rendered = f"{name}(\n{pairs}\n)"
        else:
            pairs = ", ".join(f'{key}="{value}"' for key, value in arguments.items())
            rendered = f"{name}({pairs})"
        print(f"\n🤖 Model → Tool:\n{rendered}")

    def _log_tool_result(self, result: dict) -> None:
        if not self.verbose:
            return
        print("\n🔧 Tool Result:")
        if not result.get("success", False):
            print(result.get("message") or json.dumps(result, ensure_ascii=False))
            return
        if result.get("patient_name"):
            print(
                f"نوبت ثبت شد ✓  {result['patient_name']} | "
                f"{result['day']} {result['time']} | {result.get('reason', '-')}"
            )
            return
        slots = result.get("available_slots")
        if isinstance(slots, dict):
            lines = [f"{day} {time}" for day, times in slots.items() for time in times]
            print("\n".join(lines) if lines else "(هیچ نوبت خالی وجود ندارد)")
        elif isinstance(slots, list):
            day = result.get("day", "")
            print("\n".join(f"{day} {time}".strip() for time in slots) if slots else "(هیچ نوبت خالی وجود ندارد)")
        else:
            print(json.dumps(result, ensure_ascii=False))
