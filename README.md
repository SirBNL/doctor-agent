<!-- ─────────────────────────── HEADER ─────────────────────────── -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,20&height=210&section=header&text=Doctor%20Appointment%20Agent&fontSize=46&fontColor=ffffff&animation=twonesided&desc=Persian-speaking%20AI%20that%20actually%20books%20appointments%20%E2%80%94%20with%20OR%20without%20any%20LLM&descSize=17&descAlignY=64" width="100%" alt="header"/>

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Ollama](https://img.shields.io/badge/%F0%9F%A6%99-Ollama%20Tool%20Calling-8B5CF6?style=for-the-badge)](https://ollama.com/)
[![No-LLM mode](https://img.shields.io/badge/%F0%9F%A7%A0-Works%20WITHOUT%20any%20LLM-EC4899?style=for-the-badge)](#-three-brains-one-body)
[![Tests](https://img.shields.io/badge/Tests-56%20passing-10B981?style=for-the-badge&logo=pytest&logoColor=white)](#-testing)
[![CI](https://img.shields.io/github/actions/workflow/status/SirBNL/doctor-agent/ci.yml?branch=main&style=for-the-badge&label=CI)](../../actions)
[![License](https://img.shields.io/badge/License-MIT-F59E0B?style=for-the-badge)](LICENSE)

<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=22&pause=900&color=10B981&center=true&vCenter=true&width=660&lines=Talk+in+Persian+%F0%9F%87%AE%F0%9F%87%B7+%E2%86%92+Real+appointment+booked;Runs+with+Ollama+local+LLMs+%E2%80%A6+or+with+ZERO+models;Built-in+brain+runs+100%25+offline+%E2%80%94+no+download%2C+no+GPU;56+tests+%E2%9C%94+0+dependencies+for+the+web+app" alt="typing"/>

**English** · [**فارسی**](README.fa.md)

`56 tests` · `2 real tools` · `0 deps for the web app` · `100% offline-capable`

</div>

---

## ✨ What is this?

A production-style **AI booking agent** that speaks Persian. You type:

> «اسمم پوریاست، برای چکاپ نوبت میخوام»

…and the LLM decides — **on its own** — to call `get_available_slots`, reads the clinic schedule, calls `book_appointment`, and confirms:

> «نوبت چکاپ شما برای شنبه ساعت 09:00 ثبت شد، پوریا عزیز.»

The model never "guesses" availability. Every fact comes from a real tool result fed back with `role="tool"`, exactly like the standard OpenAI/Ollama tool-calling protocol — with `temperature=0` for deterministic, reproducible behavior. No if-else intent matching anywhere: **the LLM is the brain, the tools are its hands.**

And here is the twist most agents don't have: **you don't even need an LLM to run it.** A built-in scripted brain can drive the exact same loop, tools and clinic memory — fully offline. Details below. 👇

## 🎬 Live Demo

<div align="center">

<img src="docs/screenshots/demo.gif" width="820" alt="demo gif — typing → tool trace → booking confirmed"/>

*Typing in Persian → agent inspects the real schedule via tools → appointment confirmed.*

</div>

| Booking card + tool chips | Expanded tool trace | Dark mode | Mobile |
|:---:|:---:|:---:|:---:|
| ![booking](docs/screenshots/web-booking.png) | ![trace](docs/screenshots/web-trace.png) | ![dark](docs/screenshots/web-dark.png) | ![mobile](docs/screenshots/mobile.png) |

## 🧠 Three brains, one body

The whole agent is engine-agnostic. Pick the brain that fits your moment:

```mermaid
flowchart LR
    U["👤 You (Persian, RTL)"] --> P{{"🧩 choose a brain"}}
    P -->|"web_app.py --mock<br/>main.py --demo"| B["🧠 Built-in smart brain<br/><sub>scripted decisions • zero LLM • 100% offline</sub>"]
    P -->|"python main.py<br/>python web_app.py"| O["🦙 Your local Ollama<br/><sub>qwen3 / llama3 / mistral … any tools-capable model</sub>"]
    B --> T["🔧 Real clinic tools<br/><sub>slots • booking • memory • normalization</sub>"]
    O --> T
    T --> R["✅ Real appointment booked"]
```

| | 🧠 Built-in brain | 🦙 Ollama (local LLM) |
|---|---|---|
| LLM required | **none** | any `tools`-capable model |
| Download size | **0 bytes** | 4 GB … 20 GB |
| Internet | **not needed** | not needed |
| Installs | **nothing** (bare Python) | `pip install -r requirements.txt` |
| Tool-calling loop | ✅ same loop, scripted decisions | ✅ real model decisions |
| Best for | instant demo, CI, learning, tests | production-like behavior |

> 💡 **Try it right now — 10 seconds, zero setup.** If you have Python 3.11+, you already have everything:
>
> ```bash
> python main.py --demo          # terminal demo — no pip install, no Ollama, no internet
> python web_app.py --mock       # full web UI with the built-in brain
> ```
>
> The tools, the clinic memory, the Persian normalization and the whole loop are **real** — only the *decisions* come from the scripted brain instead of a neural net. Flip to a real LLM later with one flag (`--model …`); nothing else changes.

## ⚙️ How it works

```mermaid
sequenceDiagram
    autonumber
    participant U as 👤 User
    participant A as 🤖 Agent loop
    participant O as 🧠 Brain (LLM or built-in)
    participant T as 🔧 Clinic tools

    U->>A: «اسمم پوریاست، برای چکاپ نوبت میخوام»
    A->>O: chat(messages, tools=[slots, book])
    O-->>A: tool_call → get_available_slots()
    A->>T: execute_tool (safe registry, no eval)
    T-->>A: { "شنبه 09:00", "شنبه 10:00", … }
    A->>O: history + role="tool" result
    O-->>A: tool_call → book_appointment(patient="پوریا", day="شنبه", time="09:00")
    A->>T: book it
    T-->>A: { success: true }
    A->>O: history + role="tool" result
    O-->>A: final natural Persian reply
    A-->>U: «نوبت چکاپ شما برای شنبه ساعت 09:00 ثبت شد»
```

**Built-in safety rails:** invalid tool name → structured error back to the model so it self-corrects · malformed arguments → `Invalid arguments` retry · infinite loop guard (`MAX_TOOL_ITERATIONS=8`) · `<think>` tags stripped automatically (Qwen3) · every raw Ollama error translated into clear Persian guidance.

## 🚀 Quick Start

### 🅰️ The 10-second path — no LLM, no downloads

```bash
cd doctor-agent
python main.py --demo       # interactive chat with the built-in brain
python web_app.py --mock    # …or the full web UI
```

### 🅱️ The full path — your local LLM

```bash
# 1) Install Ollama → https://ollama.com/download, then:
ollama pull huihui_ai/qwen3-coder-abliterated:30b-a3b   # or any tool-capable model

# 2) Install deps (only 2: ollama + pytest)
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3) Chat!
python main.py        # auto-picks the best installed model
python web_app.py     # …or the web app (auto-opens your browser)
```

> 💡 Not sure whether your model supports tools? `python main.py --doctor` checks connectivity, lists models, tests each one's `tools` capability and auto-picks the best installed model — so a missing exact tag is never fatal.

## 🌐 Web App — zero dependencies, all local

`web_app.py` is pure **Python standard library** (no Flask, no Node). Browsers block public pages from calling `localhost:11434` (CORS / Private Network), so the bullet-proof path is running the app on your own machine:

```text
your browser ──▶ http://localhost:8000 (web_app.py) ──▶ http://localhost:11434 (Ollama)
                     everything stays local — no CORS, no setup, no extra install
```

- 🇮🇷 Full RTL Persian chat, light/dark themes, mobile-friendly
- 🔍 Expandable **tool-trace chips** (arguments, JSON result, execution time in ms)
- ✅ Green **"نوبت شما ثبت شد"** card with full appointment details
- 🧠 Model picker — including the built-in **«مغز هوشمند محلی»** brain that needs **no model at all**
- 🎛️ Quick-action chips for one-click scenarios
- 🔒 Optional `--token` API lock, 🌍 `--share` public tunnel (cloudflared/ngrok)

```bash
python web_app.py                # run + auto-open browser (http://localhost:8000)
python web_app.py --mock         # full demo, built-in brain, zero models
python web_app.py --share --token s3cret   # public link + API lock
python web_app.py --host 0.0.0.0 --port 8080   # reach from your phone on same Wi-Fi
```

## 🇮🇷 Persian NLU you don't have to think about

The tool layer normalizes everything before the clinic logic sees it:

| User says (any form) | Understood as |
|---|---|
| «سه شنبه» / «سه‌شنبه» / Arabic digits | canonical `سه‌شنبه` |
| «۱۵» / «١٥» / "15" | `15` |
| «۳ عصر» / «10 صبح» / «۸ شب» | `15:00` / `10:00` / `20:00` |
| «امروز» / «فردا» / «پس فردا» | mapped through the clinic week (starts Saturday) |
| «پوریاست» (name glued to verb) | patient `پوریا` |

## 📁 Project Structure

```text
doctor-agent/
├── main.py               # CLI entry: interactive chat, --demo, --doctor, --model, --host
├── agent.py              # DoctorAppointmentAgent — the tool-calling loop + error translation
├── tools.py              # 2 tools + Persian normalization + safe TOOL_REGISTRY (no eval)
├── data.py               # Mock clinic: doctor schedule + in-memory bookings (ClinicState)
├── config.py             # MODEL, temperature=0, loop guard, the 9-rule Persian system prompt
├── diagnostics.py        # auto model resolution + --doctor full diagnostics (urllib only)
├── check_model.py        # one-shot "does this model really emit tool_calls?" tester
├── web_app.py            # stdlib-only web app (chat UI + REST API + tunnel sharing)
├── static/               # index.html · app.css · app.js  (RTL, dark/light, zero deps)
├── docs/screenshots/     # demo.gif + UI screenshots used by this README
├── tests/                # test_tools · test_agent · test_diagnostics  (56 tests)
├── requirements.txt      # ollama, pytest — that's all
└── LICENSE               # MIT
```

## 🧪 Testing

**56 tests**, zero external services — the model is replaced by a scripted client, so the suite runs anywhere in ~0.2s:

```bash
pytest -v
```

- `test_tools.py` — time/day normalization, slots, booking, duplicates, closed days, safe dispatch
- `test_agent.py` — all README scenarios end-to-end + Unknown tool / Invalid arguments / loop guard
- `test_diagnostics.py` — model resolution, capability probing, doctor report

## 🛠️ Model Guide

<details>
<summary><b>Which models work? (click to expand)</b></summary>

| Model | Verdict for this project |
|---|---|
| `huihui_ai/qwen3-coder-abliterated:30b-a3b` | ⭐ default — MoE, only 3B active params, native tool calling, fast even on CPU |
| `qwen3:4b` / `qwen2.5:7b` / `llama3.1:8b` / `mistral-nemo` | solid classic choices (~4-8 GB) |
| `minimax-m3:cloud` | cloud model — needs `ollama signin` + internet |
| `alduin-4b` (Persian-friendly) | light, but verify with `python check_model.py --model …` first |

Rule of thumb: the model **must** support Ollama's `tools` capability — check with `ollama show <model>` (look for `tools`) or `python check_model.py`. And remember: no model at all is also a valid choice — the built-in brain (section above) runs everything.
</details>

## 🧯 Troubleshooting

<details>
<summary><b>Something not working? (click to expand)</b></summary>

| Symptom | Fix |
|---|---|
| `Connection refused` | start Ollama: `ollama serve` — then `python main.py --doctor` |
| `model … not found` | app auto-picks the closest installed model; install yours: `ollama pull <model>` |
| Model chats but never books | model lacks the `tools` capability → pick another (table above) |
| Web app can't reach Ollama | run the web app locally (`python web_app.py`) — that's the no-CORS path |
| Persian looks broken in Windows terminal | `set PYTHONUTF8=1` |
| «حداکثر تعداد فراخوانی Tool پر شد» | raise `MAX_TOOL_ITERATIONS` in `config.py` |
| No GPU / no internet at all? | you're fine: `python main.py --demo` or `python web_app.py --mock` |

> 🩺 **One command for almost everything:** `python main.py --doctor`
</details>

## 🗺️ Roadmap

- [ ] Streaming token output (Ollama NDJSON → SSE)
- [ ] Multi-provider fallback (OpenAI / DeepSeek / Groq …)
- [ ] Telegram bot with inline keyboards
- [ ] Google Calendar export
- [ ] Persistent storage (SQLite) instead of in-memory state

## 🤝 Contributing

PRs are welcome! For anything non-trivial, open an issue first. Run `pytest -v` before submitting — the whole suite must stay green and Ollama-free.

## 📄 License

[MIT](LICENSE) — free to use, modify and ship. If this repo helped you, a ⭐ would make our day.

## 🐍 Contribution Snake

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/SirBNL/doctor-agent/output/github-contribution-grid-snake-dark.svg"/>
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/SirBNL/doctor-agent/output/github-contribution-grid-snake.svg"/>
  <img alt="contribution snake" src="https://raw.githubusercontent.com/SirBNL/doctor-agent/output/github-contribution-grid-snake.svg"/>
</picture>

</div>

## 📊 GitHub Stats

<div align="center">

<img src="https://skillicons.dev/icons?i=python,pytest,html,css,js&theme=dark" alt="stack"/>

<img src="https://github-readme-stats.vercel.app/api?username=SirBNL&show_icons=true&theme=tokyonight&hide_border=true&count_private=true" height="150" alt="stats"/>
<img src="https://github-readme-stats.vercel.app/api/top-langs/?username=SirBNL&layout=compact&theme=tokyonight&hide_border=true" height="150" alt="langs"/>

<sub>Made with ❤️ and `temperature=0` — deterministic, testable, honest AI.</sub>

</div>

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,20&height=120&section=footer" width="100%" alt="footer"/>
