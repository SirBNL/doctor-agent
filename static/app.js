/* دستیار نوبت کلینیک — منطق سمت مرورگر (بدون هیچ کتابخانه) */
"use strict";

// ---------------------------------------------------------------------------
// ابزارهای کوچک
// ---------------------------------------------------------------------------

const $ = (sel) => document.querySelector(sel);

const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
function faDigits(text) {
  return String(text).replace(/\d/g, (d) => FA_DIGITS[d]);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text);
  return div.innerHTML;
}

function scrollToBottom() {
  const wrap = $(".chat-wrap");
  wrap.scrollTop = wrap.scrollHeight;
}

function nowTime() {
  const t = new Date();
  return faDigits(
    `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`
  );
}

// ---------------------------------------------------------------------------
// وضعیت برنامه
// ---------------------------------------------------------------------------

const state = {
  busy: false,
  health: null,
  model: null,
};

const TOOL_LABELS = {
  get_available_slots: "🔧 بررسی نوبت‌های آزاد",
  book_appointment: "🔧 ثبت نوبت",
};

// ---------------------------------------------------------------------------
// رندر پیام‌ها
// ---------------------------------------------------------------------------

function removeWelcome() {
  const welcome = $(".welcome");
  if (welcome) welcome.remove();
}

function addUserMessage(text) {
  removeWelcome();
  const el = document.createElement("div");
  el.className = "msg user";
  el.innerHTML = `${escapeHtml(text)}<span class="who">${nowTime()}</span>`;
  $("#chat").appendChild(el);
  scrollToBottom();
}

function addTyping() {
  const el = document.createElement("div");
  el.className = "typing";
  el.id = "typing";
  el.innerHTML = `<span class="dots"><i></i><i></i><i></i></span><span id="typing-sec">در حال فکر کردن…</span>`;
  $("#chat").appendChild(el);
  scrollToBottom();
  const started = Date.now();
  const timer = setInterval(() => {
    const sec = Math.floor((Date.now() - started) / 1000);
    const label = $("#typing-sec");
    if (!label) { clearInterval(timer); return; }
    label.textContent = sec < 3 ? "در حال فکر کردن…" : `مدل در حال اجراست… ${faDigits(sec)} ثانیه`;
  }, 500);
  return () => clearInterval(timer);
}

function addTraceChips(trace) {
  if (!Array.isArray(trace) || trace.length === 0) return;
  const wrap = document.createElement("div");
  wrap.className = "trace";
  for (const step of trace) {
    const chip = document.createElement("details");
    chip.className = "tool-chip";
    const label = TOOL_LABELS[step.name] || `🔧 ${step.name}`;
    const okMark = step.result && step.result.success ? " ✓" : " ✗";
    chip.innerHTML =
      `<summary>${label}${okMark} <small>${faDigits(Math.round(step.duration_ms || 0))}ms</small></summary>` +
      `<div class="tool-pop">args: ${escapeHtml(JSON.stringify(step.arguments || {}, null, 1))}\nresult: ${escapeHtml(JSON.stringify(step.result, null, 1))}</div>`;
    wrap.appendChild(chip);
  }
  $("#chat").appendChild(wrap);
}

function addBookingCard(appt) {
  const el = document.createElement("div");
  el.className = "booking-card";
  el.innerHTML = `
    <div class="bk-head">✅ نوبت شما ثبت شد</div>
    <div class="bk-grid">
      <div><b>بیمار</b><span>${escapeHtml(appt.patient_name)}</span></div>
      <div><b>روز</b><span>${escapeHtml(appt.day)}</span></div>
      <div><b>ساعت</b><span>${escapeHtml(faDigits(appt.time))}</span></div>
      <div><b>دلیل مراجعه</b><span>${escapeHtml(appt.reason || "—")}</span></div>
    </div>`;
  $("#chat").appendChild(el);
}

function addBotMessage(text, { error = false } = {}) {
  const el = document.createElement("div");
  el.className = `msg bot${error ? " error" : ""}`;
  el.innerHTML = `${escapeHtml(text)}<span class="who">${nowTime()}</span>`;
  $("#chat").appendChild(el);
  scrollToBottom();
}

/** یک پیام خطا با راهنمای کوتاه رفع مشکل زیرش */
function addErrorWithHelp(message) {
  addBotMessage(message, { error: true });
  if (/اتصال به سرویس Ollama|نصب نیست|Tool Calling|timeout/.test(message)) {
    const el = document.createElement("div");
    el.className = "msg bot";
    el.style.fontSize = "12px";
    el.innerHTML =
      `<span class="who">💡 راهنمای سریع</span>` +
      `۱) سرویس Ollama روشن است؟ <code dir="ltr">ollama serve</code><br>` +
      `۲) عیب‌یابی کامل با یک دستور: <code dir="ltr">python main.py --doctor</code><br>` +
      `۳) دمو بدون مدل: <code dir="ltr">python web_app.py --mock</code>`;
    $("#chat").appendChild(el);
  }
  scrollToBottom();
}

// ---------------------------------------------------------------------------
// وضعیت هدر (اتصال + مدل)
// ---------------------------------------------------------------------------

function setStatus(kind, text) {
  const pill = $("#status-pill");
  pill.className = `status-pill ${kind}`;
  $("#status-text").textContent = text;
}

function populateModels(models, current) {
  const select = $("#model-select");
  select.innerHTML = "";
  for (const m of models) {
    const opt = document.createElement("option");
    opt.value = m.name;
    const badge = m.tools === false ? " (بدون ابزار)" : "";
    opt.textContent = m.name + badge;
    select.appendChild(opt);
  }
  if (current) select.value = current;
  select.disabled = models.length === 0;
}

async function loadHealth() {
  try {
    const res = await fetch("/api/health", { cache: "no-store" });
    const data = await res.json();
    state.health = data;
    state.model = data.model;
    populateModels(data.models || [], data.model);
    $("#foot-model").textContent = `مدل: ${data.model}`;
    if (data.mock) {
      setStatus("ok", "دموی شبیه‌ساز فعال است");
      $("#foot-model").textContent = "دموی شبیه‌ساز (بدون Ollama)";
      return;
    }
    if (data.ollama_reachable) {
      setStatus("ok", "Ollama متصل است");
      if (data.model_note) {
        showHelp(`ℹ️ ${data.model_note}`);
      }
      const noTools = (data.models || []).every((m) => m.tools === false);
      if (noTools) {
        showHelp(
          "⚠️ هیچ‌کدام از مدل‌های نصب‌شده از Tool Calling پشتیبانی نمی‌کنند. " +
            "پیشنهاد: <code dir='ltr'>ollama pull qwen3:4b</code> یا یک مدل qwen دیگر."
        );
      }
    } else {
      setStatus("fail", "Ollama در دسترس نیست");
      showHelp(
        "⚠️ اتصال به Ollama برقرار نشد. سرویس را اجرا کنید: <code dir='ltr'>ollama serve</code> " +
          "(در ویندوز آیکن Ollama کنار ساعت) — عیب‌یابی: <code dir='ltr'>python main.py --doctor</code>"
      );
    }
    if (data.start_error) {
      showHelp("⚠️ " + escapeHtml(data.start_error) + " — راه‌حل: <code dir='ltr'>pip install -r requirements.txt</code>");
    }
  } catch {
    setStatus("fail", "سرور وب در دسترس نیست");
  }
}

function showHelp(html) {
  const banner = $("#help-banner");
  banner.innerHTML = html;
  banner.classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// ارسال پیام
// ---------------------------------------------------------------------------

async function sendMessage(text) {
  const trimmed = text.trim();
  if (!trimmed || state.busy) return;
  state.busy = true;
  $("#btn-send").disabled = true;
  addUserMessage(trimmed);
  $("#input").value = "";
  autoGrow();
  const stopTyping = addTyping();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: trimmed }),
    });
    const data = await res.json();

    if (!data.ok) {
      addErrorWithHelp(data.error || "خطای نامشخص رخ داد.");
      return;
    }
    addTraceChips(data.trace);
    for (const step of data.trace || []) {
      if (step.name === "book_appointment" && step.result && step.result.success) {
        addBookingCard(step.result);
      }
    }
    addBotMessage(data.reply || "…");
  } catch {
    addErrorWithHelp("ارتباط با سرور وب قطع شد؛ آیا python web_app.py هنوز در حال اجراست؟");
  } finally {
    stopTyping();
    $("#typing")?.remove();
    state.busy = false;
    $("#btn-send").disabled = false;
    $("#input").focus();
  }
}

// ---------------------------------------------------------------------------
// رویدادها
// ---------------------------------------------------------------------------

function autoGrow() {
  const input = $("#input");
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 130) + "px";
}

$("#btn-send").addEventListener("click", () => sendMessage($("#input").value));

$("#input").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey) {
    ev.preventDefault();
    sendMessage($("#input").value);
  }
});
$("#input").addEventListener("input", autoGrow);

$("#quick-chips").addEventListener("click", (ev) => {
  const chip = ev.target.closest(".chip");
  if (chip) sendMessage(chip.dataset.text);
});

$("#btn-reset").addEventListener("click", async () => {
  if (state.busy) return;
  await fetch("/api/reset", { method: "POST" });
  $("#chat").innerHTML = "";
  location.reload();
});

$("#model-select").addEventListener("change", async (ev) => {
  const model = ev.target.value;
  if (!model || state.health?.mock) return;
  const res = await fetch("/api/model", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  const data = await res.json();
  if (data.ok) {
    state.model = model;
    $("#foot-model").textContent = `مدل: ${model}`;
    setStatus("ok", "Ollama متصل است");
    $("#help-banner").classList.add("hidden");
  } else {
    showHelp(`⚠️ ${escapeHtml(data.error || "تغییر مدل ناموفق بود.")}`);
  }
});

// ---------------------------------------------------------------------------
// شروع
// ---------------------------------------------------------------------------

loadHealth();
$("#input").focus();
