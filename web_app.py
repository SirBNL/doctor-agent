"""وب‌اپلیکیشن محلی دستیار نوبت پزشک — بدون هیچ وابستگی جدید (فقط کتابخانه استاندارد).

چرا این فایل؟
    مرورگرها اجازه نمی‌دهند یک صفحهٔ اینترنتی (https) مستقیم به Ollama لوکال شما
    وصل شود (محدودیت CORS/Private Network — حتی با OLLAMA_ORIGINS). ولی وقتی این
    وب‌اپ روی سیستم خودتان اجرا شود، زنجیرهٔ اتصال همیشه لوکال است و هیچ محدودیتی
    وجود ندارد:

        مرورگر شما ──▶ http://localhost:8000 (همین برنامه) ──▶ http://localhost:11434 (Ollama)

اجرا:
    python web_app.py                 # اجرا + باز شدن خودکار مرورگر
    python web_app.py --port 8080     # پورت دلخواه
    python web_app.py --mock          # دموی کامل بدون نیاز به مدل (شبیه‌ساز)
    python web_app.py --share         # اشتراک‌گذاری عمومی با تونل (cloudflared/ngrok)
    python web_app.py --token s3cret  # قفل کردن API با توکن (پیشنهادی در حالت share)
    python web_app.py --host 0.0.0.0  # دسترسی از گوشی در همان شبکهٔ وای‌فای
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from agent import DoctorAppointmentAgent  # noqa: E402
from config import MODEL, OLLAMA_HOST  # noqa: E402
from diagnostics import list_models, normalize_host, resolve_model, supports_tools  # noqa: E402
from main import DemoModelClient, _demo_plans, _enable_utf8_stdio  # noqa: E402
from tools import reset_clinic_state, tools_state_snapshot  # noqa: E402

STATIC_DIR = BASE_DIR / "static"

# ---------------------------------------------------------------------------
# استخر Agent (یک نمونهٔ سراسری با قفل — کافی برای استفادهٔ محلی/تونل)
# ---------------------------------------------------------------------------


class AgentPool:
    """مدیریت مدل فعال + قفل اجرا؛ در حالت mock از شبیه‌ساز استفاده می‌کند."""

    def __init__(self, mock: bool, host: str, desired_model: str) -> None:
        self.mock = mock
        self.host = normalize_host(host)
        self.lock = threading.Lock()
        self.model_note: str | None = None
        self.models_cache: list[dict] = []
        self.start_error: str | None = None
        if mock:
            self.model = "مغز هوشمند محلی"
            self.agent = DoctorAppointmentAgent(
                client=DemoModelClient(_demo_plans()), verbose=False
            )
        else:
            self.model, self.model_note = resolve_model(self.host, desired_model)
            try:
                self.agent = DoctorAppointmentAgent(model=self.model, host=self.host)
            except RuntimeError as exc:
                # کتابخانه ollama نصب نیست؛ سرور را بالا می‌آوریم تا حداقل UI و
                # راهنمای فارسی نمایش داده شود (خطا در /api/chat و /api/health)
                self.agent = None
                self.start_error = str(exc)

    # ------------------------------ عملیات ------------------------------

    def chat(self, message: str) -> dict:
        if self.agent is None:
            return {"ok": False, "error": self.start_error or "Agent آماده نیست."}
        with self.lock:
            try:
                reply = self.agent.chat(message)
            except RuntimeError as exc:
                return {"ok": False, "error": str(exc)}
            return {"ok": True, "reply": reply, "trace": self.agent.last_trace}

    def reset(self) -> None:
        if self.agent is None:
            return
        with self.lock:
            self.agent.reset()
            reset_clinic_state()

    def bookings(self) -> list[dict]:
        return tools_state_snapshot()

    def set_model(self, model: str) -> dict:
        if self.mock:
            return {"ok": False, "error": "در حالت mock تغییر مدل ممکن نیست."}
        try:
            installed = list_models(self.host)
        except Exception as exc:  # سرور قطع است
            return {"ok": False, "error": f"اتصال به Ollama برقرار نشد: {exc}"}
        if model not in installed:
            return {"ok": False, "error": f"مدل «{model}» نصب نیست."}
        with self.lock:
            self.model = model
            try:
                self.agent = DoctorAppointmentAgent(model=model, host=self.host)
                self.start_error = None
            except RuntimeError as exc:
                self.agent = None
                return {"ok": False, "error": str(exc)}
        return {"ok": True, "model": model}

    def health(self) -> dict:
        payload: dict = {
            "ok": True,
            "mock": self.mock,
            "host": self.host,
            "model": self.model,
            "model_note": self.model_note,
        }
        if self.start_error:
            payload["start_error"] = self.start_error
        if self.mock:
            payload["models"] = [{"name": "مغز هوشمند محلی", "tools": True, "size_gb": 0}]
            payload["ollama_reachable"] = False
            return payload
        try:
            names = list_models(self.host)
            payload["ollama_reachable"] = True
            payload["models"] = [
                {"name": n, "tools": supports_tools(self.host, n)} for n in names
            ]
        except Exception:
            payload["ollama_reachable"] = False
            payload["models"] = []
        return payload


# ---------------------------------------------------------------------------
# سرور HTTP
# ---------------------------------------------------------------------------

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class ClinicHandler(BaseHTTPRequestHandler):
    server_version = "ClinicAgent/1.0"
    pool: AgentPool
    token: str | None = None

    # ------------------------------ ابزارها ------------------------------

    def log_message(self, fmt: str, *args) -> None:  # لاگ کوتاه بدون نویز
        sys.stdout.write("• %s\n" % (fmt % args))

    def _authorized(self) -> bool:
        if not self.token:
            return True
        got = self.headers.get("X-Token", "")
        if not got:
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(self.path).query)
            got = (qs.get("token") or [""])[0]
        return got == self.token

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _static_file(self, name: str) -> None:
        path = (STATIC_DIR / name).resolve()
        if not str(path).startswith(str(STATIC_DIR.resolve())) or not path.is_file():
            self._json({"error": "not found"}, 404)
            return
        ctype = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
        self._send(200, path.read_bytes(), ctype)

    # ------------------------------ GET ------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._static_file("index.html")
        elif path.startswith("/static/"):
            self._static_file(path.removeprefix("/static/"))
        elif path == "/api/health":
            if not self._authorized():
                self._json({"error": "توکن نامعتبر است."}, 401)
                return
            self._json(self.pool.health())
        elif path == "/api/bookings":
            if not self._authorized():
                self._json({"error": "توکن نامعتبر است."}, 401)
                return
            self._json({"ok": True, "bookings": self.pool.bookings()})
        else:
            self._json({"error": "not found"}, 404)

    # ------------------------------ POST ------------------------------

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in ("/api/chat", "/api/reset", "/api/model"):
            self._json({"error": "not found"}, 404)
            return
        if not self._authorized():
            self._json({"error": "توکن نامعتبر است. در URL ?token=... را اضافه کنید."}, 401)
            return
        payload = self._read_json()

        if path == "/api/chat":
            message = str(payload.get("message", "")).strip()
            if not message:
                self._json({"ok": False, "error": "پیام خالی است."}, 400)
                return
            self._json(self.pool.chat(message))
        elif path == "/api/reset":
            self.pool.reset()
            self._json({"ok": True})
        elif path == "/api/model":
            model = str(payload.get("model", "")).strip()
            if not model:
                self._json({"ok": False, "error": "نام مدل خالی است."}, 400)
                return
            self._json(self.pool.set_model(model))


# ---------------------------------------------------------------------------
# اشتراک‌گذاری عمومی با تونل (ایدهٔ «بقیه هم با وب من کار کنند»)
# ---------------------------------------------------------------------------

def try_start_tunnel(port: int) -> str | None:
    """اگر cloudflared یا ngrok نصب بود، تونل عمومی می‌سازد و URL را برمی‌گرداند."""
    if shutil.which("cloudflared"):
        try:
            print("🌐 ساخت تونل با cloudflared … (چند ثانیه صبر کنید)")
            proc = subprocess.Popen(
                ["cloudflared", "http", "--url", f"http://localhost:{port}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            import time
            deadline = time.time() + 20
            while time.time() < deadline:
                line = proc.stdout.readline() if proc.stdout else ""
                match = __import__("re").search(r"https://\S*trycloudflare\.com", line or "")
                if match:
                    return match.group(0)
            print("⚠️  تونل cloudflared در زمان مناسب آماده نشد؛ خروجی خودش را در ترمینال ببینید.")
        except Exception as exc:
            print(f"⚠️  اجرای cloudflared شکست خورد: {exc}")
    elif shutil.which("ngrok"):
        print("🌐 ngrok پیدا شد. در یک ترمینال دیگر اجرا کنید:  ngrok http %d" % port)
        print("   بعد آدرس https که ngrok می‌دهد را برای بقیه بفرستید.")
    else:
        print("ℹ️  برای اشتراک‌گذاری عمومی یکی از این دو را نصب کنید:")
        print("     • cloudflared  (پیشنهادی، بدون ثبت‌نام):  winget install Cloudflare.cloudflared")
        print("     • ngrok:  https://ngrok.com/download")
        print("   سپس:  cloudflared http --url http://localhost:%d" % port)
    return None


# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="clinic-web", description="رابط وب دستیار نوبت پزشک")
    parser.add_argument("--host", default="127.0.0.1", help="آدرس bind (برای گوشی: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ollama-host", default=OLLAMA_HOST, help="آدرس سرویس Ollama")
    parser.add_argument("--model", default=MODEL, help="مدل Ollama (پیش‌فرض: انتخاب خودکار)")
    parser.add_argument("--mock", action="store_true", help="دمو با شبیه‌ساز، بدون نیاز به Ollama/مدل")
    parser.add_argument("--share", action="store_true", help="ساخت تونل عمومی برای اشتراک‌گذاری")
    parser.add_argument("--token", default=None, help="توکن اختیاری برای قفل کردن API (حالت share)")
    parser.add_argument("--no-browser", action="store_true", help="باز نکردن خودکار مرورگر")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _enable_utf8_stdio()
    args = parse_args(argv)

    pool = AgentPool(mock=args.mock, host=args.ollama_host, desired_model=args.model)
    ClinicHandler.pool = pool
    ClinicHandler.token = args.token

    server = ThreadingHTTPServer((args.host, args.port), ClinicHandler)
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"

    print("═" * 62)
    print(" 🩺  رابط وب دستیار نوبت دکتر احمدی")
    print("═" * 62)
    print(f" آدرس محلی : {url}")
    if args.mock:
        print(" حالت      : دموی شبیه‌ساز (بدون Ollama)")
    else:
        print(f" مدل فعال  : {pool.model}")
        if pool.model_note:
            print(f" {pool.model_note}")
        if not pool.health().get("ollama_reachable"):
            print(" ⚠️  Ollama در دسترس نیست! اجرا کنید:  ollama serve")
            print("     عیب‌یابی کامل:  python main.py --doctor")
    if args.share:
        public = try_start_tunnel(args.port)
        if public:
            token_q = f"?token={args.token}" if args.token else ""
            print(f" لینک عمومی: {public}{token_q}")
            print("   هر کسی این لینک را باز کند با Ollama/کلینیک شما کار می‌کند.")
    if args.token:
        print(f" 🔒 توکن فعال است؛ لینک استفاده: {url}?token={args.token}")
    print(" توقف: Ctrl+C")
    print("═" * 62)

    if not args.no_browser:
        try:
            webbrowser.open(url + (f"?token={args.token}" if args.token else ""))
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 سرور وب بسته شد.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
