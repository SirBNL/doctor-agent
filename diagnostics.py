"""تشخیص خودکار مدل و عیب‌یابی Ollama — بدون وابستگی اضافه (فقط کتابخانه استاندارد).

این ماژول سه کار اصلی می‌کند:

    1) اتصال به Ollama با urllib و گرفتن لیست مدل‌ها (/api/tags)
    2) بررسی قابلیت Tool Calling هر مدل (/api/show → capabilities)
    3) انتخاب هوشمند بهترین مدل نصب‌شده (resolve_model) + گزارش فارسی عیب‌یابی
       (doctor_report) که با «python main.py --doctor» قابل اجراست.

هدف: اگر کاربر مدلی داشته باشد که تگ دقیقش با پیش‌فرض فرق کند (مثلاً
``30b-a3b`` به‌جای ``30b-a3b-instruct-q4_K_M``)، برنامه خودش مدل درست را پیدا
کند و به‌جای خطای «model not found»، پیام شفاف فارسی نشان دهد.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable

try:
    from config import MODEL, MODEL_PREFERENCES, OLLAMA_HOST
except ImportError:  # برای اجرای مستقل
    MODEL = "huihui_ai/qwen3-coder-abliterated:30b-a3b"
    MODEL_PREFERENCES = (r".",)
    OLLAMA_HOST = "http://localhost:11434"


# ---------------------------------------------------------------------------
# لایه ارتباط با Ollama (قابل تزریق برای تست)
# ---------------------------------------------------------------------------

Fetcher = Callable[[str, str | None], dict]


def default_fetcher(host: str) -> Fetcher:
    """یک fetcher استاندارد urllib می‌سازد: (path, payload) → dict."""
    base = normalize_host(host)

    def fetch(path: str, payload: dict | None = None, timeout: float = 4.0) -> dict:
        url = base + path
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))

    return fetch


def normalize_host(raw: str) -> str:
    """آدرس میزبان را نرمال می‌کند: افزودن http:// و حذف / انتهایی."""
    host = str(raw or OLLAMA_HOST).strip() or OLLAMA_HOST
    if not re.match(r"^https?://", host, re.IGNORECASE):
        host = f"http://{host}"
    return host.rstrip("/")


# ---------------------------------------------------------------------------
# منطق انتخاب مدل (خالص و قابل تست — بدون I/O)
# ---------------------------------------------------------------------------

def model_family(name: str) -> str:
    """بخش پایه نام مدل (قبل از تگ)؛ برای تطبیق فازی «huihui_ai/qwen3-coder-abliterated:30b-a3b»."""
    return name.split(":", 1)[0].strip().lower()


def matches_family_of(a: str, b: str) -> bool:
    """دو نام مدل هم‌خانواده‌اند اگر یکی پیشوند دیگری باشد یا پایهٔ (قبل از «:») یکی باشند."""
    a, b = str(a or "").strip().lower(), str(b or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    if model_family(a) == model_family(b):
        return True
    return a.startswith(b) or b.startswith(a)


def pick_model(
    installed: list[str],
    desired: str | None = None,
    preferences: tuple[str, ...] = MODEL_PREFERENCES,
    tool_support: dict[str, bool | None] | None = None,
) -> tuple[str, str | None]:
    """بهترین مدل را از بین مدل‌های نصب‌شده انتخاب می‌کند.

    ترتیب تصمیم:
        1) تطبیق دقیق desired
        2) تطبیق فازی: یکی پیشوند دیگری باشد یا خانواده (قبل از ":") یکی باشد
        3) بالاترین اولویت در MODEL_PREFERENCES — در هر رده، مدل دارای
           Tool Calling (در صورت دانستن) ترجیح دارد
        4) اولین مدل نصب‌شده

    خروجی: (نام مدل انتخابی، دلیل/پیام فارسی یا None)
    """
    installed = [name for name in (n.strip() for n in installed) if name]
    if not installed:
        return desired or MODEL, None

    tool_support = tool_support or {}

    def _tools_ok(name: str) -> bool:
        """True اگر بدانیم مدل Tool دارد؛ False اگر بدانیم ندارد؛ None یعنی نامعلوم."""
        return tool_support.get(name, None) is not False

    # 1) تطبیق دقیق
    if desired and desired in installed:
        return desired, None

    # 2) تطبیق فازی (پیشوندی / خانواده)
    if desired:
        desired_norm = desired.strip().lower()
        for name in installed:
            name_norm = name.lower()
            if name_norm.startswith(desired_norm) or desired_norm.startswith(name_norm):
                return name, (
                    f"مدل «{desired}» دقیقاً نصب نیست؛ نزدیک‌ترین مدل نصب‌شده "
                    f"«{name}» انتخاب شد."
                )
        desired_family = model_family(desired)
        for name in installed:
            if desired_family and model_family(name) == desired_family:
                return name, (
                    f"مدل «{desired}» دقیقاً نصب نیست؛ هم‌خانوادهٔ آن "
                    f"«{name}» انتخاب شد."
                )

    # 3) ترتیب ترجیح + ترجیح مدل‌های دارای Tool Calling در هر رده
    for pattern in preferences:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            continue
        candidates = [name for name in installed if regex.search(name)]
        if not candidates:
            continue
        with_tools = [name for name in candidates if _tools_ok(name)]
        best = (with_tools or candidates)[0]
        if not with_tools and len(candidates) > 1:
            # همهٔ رده بدون Tool بودند؛ بهترین را نگه می‌داریم ولی ادامه نمی‌دهیم چون
            # ردهٔ فعلی بالاترین اولویتِ موجود است.
            pass
        reason = None
        if desired and desired != best:
            reason = f"از مدل‌های نصب‌شده، «{best}» برای Tool Calling مناسب‌تر است."
        return best, reason

    return installed[0], None


# ---------------------------------------------------------------------------
# پرس‌وجوهای واقعی از سرور Ollama
# ---------------------------------------------------------------------------

def list_models(host: str) -> list[str]:
    """لیست مدل‌های نصب‌شده؛ در صورت عدم دسترسی خطا می‌دهد."""
    fetch = default_fetcher(host)
    data = fetch("/api/tags")
    return [
        str(m.get("name", "")).strip()
        for m in data.get("models", [])
        if str(m.get("name", "")).strip()
    ]


def model_info(host: str, model: str) -> dict[str, Any]:
    """اطلاعات مدل از /api/show: capabilities، اندازه، خانواده (یا {} در خطا)."""
    fetch = default_fetcher(host)
    try:
        return fetch("/api/show", {"model": model}, timeout=8)
    except Exception:
        return {}


def supports_tools(host: str, model: str) -> bool | None:
    """True/False اگر قابلیت «tools» معلوم باشد؛ None اگر نتوان تشخیص داد."""
    info = model_info(host, model)
    caps = info.get("capabilities")
    if isinstance(caps, list):
        return "tools" in {str(c).lower() for c in caps}
    return None


def resolve_model(host: str, desired: str | None = None) -> tuple[str, str | None]:
    """انتخاب مدل با اطلاعات واقعی سرور (لیست + قابلیت tools).

    خروجی: (model، پیام فارسی یا None). اگر سرور در دسترس نباشد همان desired
    برمی‌گردد تا پیام خطای اتصال به کاربر نشان داده شود.
    """
    try:
        installed = list_models(host)
    except Exception:
        return desired or MODEL, None

    tool_support: dict[str, bool | None] = {}
    for name in installed:
        tool_support[name] = supports_tools(host, name)

    model, reason = pick_model(installed, desired or MODEL, MODEL_PREFERENCES, tool_support)

    # اگر مدل انتخاب‌شده Tool ندارد ولی مدل دیگری دارد، همان را پیشنهاد بده
    if tool_support.get(model) is False:
        capable = [n for n, ok in tool_support.items() if ok is True]
        if capable:
            better, _ = pick_model(capable, desired or MODEL, MODEL_PREFERENCES, {})
            return better, (
                f"مدل «{model}» از Tool Calling پشتیبانی نمی‌کند؛ "
                f"«{better}» که قابلیت ابزار دارد انتخاب شد."
            )
    return model, reason


# ---------------------------------------------------------------------------
# گزارش عیب‌یابی (python main.py --doctor)
# ---------------------------------------------------------------------------

def _gb(size_bytes: Any) -> str:
    try:
        return f"{float(size_bytes) / 1024**3:.1f}GB"
    except (TypeError, ValueError):
        return "-"


def doctor_report(host: str, desired: str | None = None) -> str:
    """گزارش کامل فارسی سلامت Ollama برای نمایش در ترمینال."""
    host = normalize_host(host)
    desired = desired or MODEL
    lines: list[str] = []
    add = lines.append

    add("════════════════════════════════════════════════")
    add(" 🔍 عیب‌یابی اتصال به Ollama")
    add("════════════════════════════════════════════════")
    add(f" میزبان: {host}")

    # ۱) دسترسی سرور
    try:
        fetch = default_fetcher(host)
        version = fetch("/api/version", timeout=4).get("version", "?")
    except Exception as exc:
        add("")
        add(f" ❌ اتصال به Ollama برقرار نشد  ({type(exc).__name__})")
        add("    راه‌حل‌ها:")
        add("    ۱) سرویس را اجرا کنید:              ollama serve")
        add("    ۲) اگر ویندوز است، آیکن Ollama در کنار ساعت باید فعال باشد.")
        add("    ۳) اگر پورت را عوض کرده‌اید، با --host بدهید:  python main.py --host http://localhost:PORT")
        add("════════════════════════════════════════════════")
        return "\n".join(lines)

    add(f" ✅ سرویس در دسترس است  (نسخه {version})")

    # ۲) مدل‌های نصب‌شده
    try:
        installed = list_models(host)
    except Exception as exc:  # pragma: no cover
        add(f" ❌ گرفتن لیست مدل‌ها شکست خورد: {exc}")
        return "\n".join(lines)

    if not installed:
        add(" ⚠️  هیچ مدلی نصب نیست. مثلاً:  ollama pull qwen3:4b")
        add("════════════════════════════════════════════════")
        return "\n".join(lines)

    add(f" 📦 مدل‌های نصب‌شده: {len(installed)}")
    tool_support: dict[str, bool | None] = {}
    for name in installed:
        ok = supports_tools(host, name)
        tool_support[name] = ok
        info = model_info(host, name)
        size = _gb(info.get("model_info", {}).get("general.size") or 0)
        badge = "✓ ابزار" if ok is True else ("✗ بدون ابزار" if ok is False else "؟ نامعلوم")
        add(f"    • {name}  [{badge}]  {size}")

    # ۳) انتخاب خودکار
    model, reason = resolve_model(host, desired)
    add("")
    add(f" 🎯 مدل انتخاب‌شده برای اجرا: {model}")
    if reason:
        add(f"    {reason}")

    # ۴) نکته حالت وب مستقیم
    add("")
    add(" 💡 نکته رابط وب:")
    add("    • اجرای بدون دردسر روی همین سیستم:   python web_app.py")
    add("    • برای حالت «اتصال مستقیم از مرورگر» در سایت، باید Ollama با مجوز CORS اجرا شود:")
    add('        Windows (PowerShell):  $env:OLLAMA_ORIGINS="*"; ollama serve')
    add("      و بعد از setx حتماً Ollama را از کنار ساعت کامل ببندید و دوباره باز کنید.")
    add("════════════════════════════════════════════════")
    return "\n".join(lines)
