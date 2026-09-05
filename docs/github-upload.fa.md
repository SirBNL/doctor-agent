# 🚀 راهنمای آپلود پروژه روی GitHub (قدم‌به‌قدم)

این راهنما را از بالا به پایین اجرا کنید؛ ۵ دقیقه بیشتر نمی‌برد.

---

## ۱) جایگزین کردن نام کاربری (مهم!)

در دو فایل `README.md` و `README.fa.md` عبارت `YOUR-USERNAME` را با نام کاربری گیت‌هاب خودتان عوض کنید (برای بج CI).
با VS Code: `Ctrl+Shift+H` → Search: `YOUR-USERNAME` → Replace: نام کاربری شما → Replace All.

---

## ۲) ساخت ریپو در گیت‌هاب

1. به [github.com/new](https://github.com/new) بروید و وارد شوید.
2. **Repository name:** `doctor-agent`
3. **Public** را انتخاب کنید (برای بج‌ها، GIF و دیده‌شدن پروژه).
4. ⚠️ هیچ‌کدام از گزینه‌های «Add a README / .gitignore / license» را **تیک نزنید** — همه این‌ها داخل پروژه آماده است.
5. دکمه **Create repository**.

---

## ۳) آپلود با Git (ترمینال)

وارد پوشه پروژه شوید و این ۵ دستور را بزنید:

```bash
cd doctor-agent

git init
git add .
git commit -m "🩺 Doctor Appointment Agent — Persian AI with Ollama Tool Calling"
git branch -M main
git remote add origin https://github.com/USERNAME-شما/doctor-agent.git
git push -u origin main
```

> اگر از ویندوز استفاده می‌کنید و Git ندارید: [git-scm.com/downloads](https://git-scm.com/downloads)
> بار اول پنجره ورود گیت‌هاب باز می‌شود (یا از Personal Access Token استفاده کنید: GitHub → Settings → Developer settings → Tokens).

تمام! حالا صفحه ریپو را رفرش کنید — README زیبا با انیمیشن و GIF نمایش داده می‌شود. 🎉

---

## ۴) کارهای کوچک ولی تأثیرگذار بعد از آپلود

| کار | کجا |
|---|---|
| **About** (توضیح یک‌خطی + موضوع): `Persian AI appointment booking agent with Ollama Tool Calling` | آیکن ⚙️ کنار About در بالای ریپو |
| **Topics:** `ollama` `agent` `tool-calling` `persian` `llm` `chatbot` `python` `clinic` `farsi` `ai` | همان بخش ⚙️ |
| **Social preview** (عکس اشتراک‌گذاری): یک اسکرین‌شات از `docs/screenshots/web-booking.png` آپلود کنید | Settings → General → Social preview |
| فعال‌سازی **CI** (تست خودکار): فایل آماده در `docs/ci.yml` است — در ریپو: **Add file → Create new file** → نام: `.github/workflows/ci.yml` → محتوای `docs/ci.yml` را Paste کنید → Commit. از این بعد هر push خودش تست می‌گیرد ✓ | تب Code یا Actions |

---

## ۵) اختیاری ولی خفن: انیمیشن مارِ GitHub (GitHub Snake)

این همان انیمیشنی است که نوارActivity شما را به مار متحرک تبدیل می‌کند:

1. در ریپو، فایل `.github/workflows/snake.yml` بسازید با این محتوا:

```yaml
name: Snake
on:
  schedule: [{cron: "0 0 * * *"}]
  workflow_dispatch:
jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: Platane/snk/svg-only@v3
        with:
          github_user_name: ${{ github.repository_owner }}
          outputs: dist/snake.svg
      - uses: crazy-max/ghaction-github-pages@v4
        with:
          target_branch: output
          build_dir: dist
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

2. یک شاخه `output` ساخته می‌شود؛ بعد در README این خط را اضافه کنید:

```markdown
<img src="https://raw.githubusercontent.com/USERNAME-شما/doctor-agent/output/snake.svg" width="100%"/>
```

3. تب Actions → Snake → Run workflow را یک بار دستی اجرا کنید.

---

## ۶) آپدیت‌های بعدی

هر وقت چیزی را عوض کردید:

```bash
git add .
git commit -m "توضیح تغییر"
git push
```

موفق باشید! ⭐
