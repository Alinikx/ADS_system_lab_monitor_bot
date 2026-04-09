import json
import os
import platform
import shutil
import subprocess
import time
import logging

import psutil
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN non impostato nelle variabili d'ambiente")

    cfg["telegram_token"] = token
    return cfg


CONFIG = load_config()
HOSTS = CONFIG.get("hosts", [])
ALLOWED_USER_IDS = set(CONFIG.get("allowed_user_ids", []))
ADMIN_CHAT_ID = CONFIG.get("admin_chat_id")

uptime_alert_sent = False


def format_bytes(num, suffix="B"):
    for unit in ["", "K", "M", "G", "T", "P"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Y{suffix}"


def get_uptime_days() -> int:
    boot_ts = psutil.boot_time()
    uptime_sec = int(time.time() - boot_ts)
    return uptime_sec // 86400


def get_pi_power_status() -> str:
    try:
        res = subprocess.run(
            ["vcgencmd", "get_throttled"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
        out = res.stdout.strip()

        if not out.startswith("throttled="):
            return f"Raw: {out}"

        val_hex = out.split("=")[1]
        val = int(val_hex, 16)

        if val == 0:
            return "OK (nessuna sottotensione o throttling rilevati)"

        msgs = []
        if val & 0x00001:
            msgs.append("sottotensione attuale")
        if val & 0x10000:
            msgs.append("sottotensione in passato")
        if val & 0x00002:
            msgs.append("CPU frequency capped ora")
        if val & 0x20000:
            msgs.append("CPU frequency capped in passato")
        if val & 0x00004:
            msgs.append("CPU throttling ora")
        if val & 0x40000:
            msgs.append("CPU throttling in passato")

        return "; ".join(msgs)

    except FileNotFoundError:
        return "vcgencmd non disponibile"
    except Exception as e:
        return f"Errore lettura power status: {e}"


def get_local_status() -> str:
    boot_ts = psutil.boot_time()
    uptime_sec = int(time.time() - boot_ts)
    days, rem = divmod(uptime_sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    uptime_str = f"{days}d {hours}h {minutes}m"

    cpu_percent = psutil.cpu_percent(interval=1)
    load1, load5, load15 = os.getloadavg()
    cpu_count = psutil.cpu_count()

    vm = psutil.virtual_memory()
    mem_used = format_bytes(vm.used)
    mem_total = format_bytes(vm.total)

    du = shutil.disk_usage("/")
    disk_used = format_bytes(du.used)
    disk_total = format_bytes(du.total)
    disk_percent = du.used / du.total * 100

    temp_str = "n/a"
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                if entries:
                    temp_str = f"{entries[0].current:.1f}°C ({name})"
                    break
    except Exception:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r", encoding="utf-8") as f:
                milli = int(f.read().strip())
            temp_str = f"{milli / 1000.0:.1f}°C"
        except Exception:
            pass

    os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
    hostname = platform.node()
    power_status = get_pi_power_status()

    text = (
        f"*System status* — `{hostname}`\n"
        f"OS: `{os_info}`\n"
        f"Uptime: `{uptime_str}`\n\n"
        f"CPU: `{cpu_percent:.1f}%` | Load avg: "
        f"`{load1:.2f} {load5:.2f} {load15:.2f}` (/{cpu_count} core)\n"
        f"RAM: `{mem_used} / {mem_total}` ({vm.percent:.1f}%)\n"
        f"Disk /: `{disk_used} / {disk_total}` ({disk_percent:.1f}%)\n"
        f"Temp: `{temp_str}`\n"
        f"Power: `{power_status}`\n"
    )

    return text


def ping_host(address: str, count: int = 2, timeout: int = 2) -> bool:
    try:
        res = subprocess.run(
            ["ping", "-c", str(count), "-W", str(timeout), address],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return res.returncode == 0
    except Exception:
        return False


def is_authorized(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    return user.id in ALLOWED_USER_IDS


async def ensure_authorized(update: Update) -> bool:
    if is_authorized(update):
        return True

    if update.message:
        await update.message.reply_text("Non sei autorizzato a usare questo bot.")
    return False


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_authorized(update):
        return

    msg = (
        "Ciao! Sono il tuo *System & Home Lab Monitor*.\n\n"
        "Comandi disponibili:\n"
        "/status - stato di questa macchina\n"
        "/hosts - elenco host monitorati\n"
        "/pingall - ping di tutti gli host del lab\n"
        "/chatid - mostra chat_id e user_id\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_authorized(update):
        return

    text = get_local_status()
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_hosts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_authorized(update):
        return

    if not HOSTS:
        await update.message.reply_text("Nessun host configurato in `config.json`.", parse_mode="Markdown")
        return

    lines = ["*Host monitorati:*"]
    for h in HOSTS:
        lines.append(f"- *{h['name']}* -> `{h['address']}`")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_pingall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_authorized(update):
        return

    if not HOSTS:
        await update.message.reply_text("Nessun host configurato in `config.json`.", parse_mode="Markdown")
        return

    await update.message.reply_text("Inizio ping degli host...")

    results = []
    for h in HOSTS:
        alive = ping_host(h["address"])
        status_icon = "OK" if alive else "KO"
        results.append(f"{status_icon} *{h['name']}* (`{h['address']}`)")

    text = "*Risultato ping host:*\n" + "\n".join(results)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    msg = (
        f"user_id: `{user.id if user else 'n/a'}`\n"
        f"chat_id: `{chat.id if chat else 'n/a'}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def check_uptime_alert(context: ContextTypes.DEFAULT_TYPE):
    global uptime_alert_sent

    if not ADMIN_CHAT_ID:
        return

    uptime_days = get_uptime_days()

    if uptime_days >= 30 and not uptime_alert_sent:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                f"⚠️ *Uptime alert*\n\n"
                f"La Raspberry ha raggiunto `{uptime_days}` giorni di uptime.\n"
                f"Valuta se fare un reboot pulito o un check manutenzione."
            ),
            parse_mode="Markdown",
        )
        uptime_alert_sent = True

    if uptime_days < 1:
        uptime_alert_sent = False


def main():
    token = CONFIG["telegram_token"]

    application = (
        ApplicationBuilder()
        .token(token)
        .build()
    )

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("hosts", cmd_hosts))
    application.add_handler(CommandHandler("pingall", cmd_pingall))
    application.add_handler(CommandHandler("chatid", cmd_chatid))

    if application.job_queue is None:
        raise RuntimeError(
            "JobQueue non disponibile. Installa python-telegram-bot con extra job-queue: "
            'pip install "python-telegram-bot[job-queue]"'
        )

    application.job_queue.run_repeating(check_uptime_alert, interval=3600, first=30)

    application.run_polling()


if __name__ == "__main__":
    main()