from asyncio import iscoroutinefunction
from html import escape
from time import time

from psutil import cpu_percent, disk_usage, virtual_memory

from bot import bot_start_time, status_dict
from bot.core.config_manager import Config
from bot.helper.telegram_helper.button_build import ButtonMaker

from .bot_utils import sync_to_async

SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


class MirrorStatus:
    STATUS_UPLOAD = "🚀 Upload"
    STATUS_DOWNLOAD = "⬇️ Download"
    STATUS_CLONE = "📂 Clone"
    STATUS_QUEUEDL = "⏳ Queue Download"
    STATUS_QUEUEUP = "⏳ Queue Upload"
    STATUS_PAUSED = "⏸️ Paused"
    STATUS_ARCHIVE = "📦 Archive"
    STATUS_EXTRACT = "📂 Extract"
    STATUS_SPLIT = "✂️ Split"
    STATUS_CHECK = "✅ Check"
    STATUS_SEED = "🌱 Seed"
    STATUS_SAMVID = "🎥 SamVid"
    STATUS_CONVERT = "🔄 Convert"
    STATUS_FFMPEG = "🎞️ FFmpeg"
    STATUS_METADATA = "📝 Metadata"
    STATUS_WATERMARK = "💧 Watermark"


STATUSES = {
    "ALL": "🗂️ All",
    "DL": MirrorStatus.STATUS_DOWNLOAD,
    "UP": MirrorStatus.STATUS_UPLOAD,
    "QD": MirrorStatus.STATUS_QUEUEDL,
    "QU": MirrorStatus.STATUS_QUEUEUP,
    "AR": MirrorStatus.STATUS_ARCHIVE,
    "EX": MirrorStatus.STATUS_EXTRACT,
    "SD": MirrorStatus.STATUS_SEED,
    "CL": MirrorStatus.STATUS_CLONE,
    "CM": MirrorStatus.STATUS_CONVERT,
    "SP": MirrorStatus.STATUS_SPLIT,
    "SV": MirrorStatus.STATUS_SAMVID,
    "FF": MirrorStatus.STATUS_FFMPEG,
    "PA": MirrorStatus.STATUS_PAUSED,
    "CK": MirrorStatus.STATUS_CHECK,
}


def get_readable_file_size(size_in_bytes):
    """Convert bytes to a human-readable file size."""
    if size_in_bytes is None:
        return "0B"
    size_units = SIZE_UNITS
    size = float(size_in_bytes)
    index = 0
    while size >= 1024 and index < len(size_units) - 1:
        size /= 1024.0
        index += 1
    return f"{size:.2f} {size_units[index]}"


def get_progress_bar_string(pct):
    if isinstance(pct, str):
        pct = float(pct.strip("%"))
    p = min(max(pct, 0), 100)
    c_full = int((p + 5) // 10)
    p_str = "●" * c_full
    p_str += "○" * (10 - c_full)
    return p_str


def get_readable_time(seconds):
    """Convert seconds to a human-readable time format."""
    seconds = int(seconds)
    periods = [
        ("y", 60 * 60 * 24 * 365),
        ("d", 60 * 60 * 24),
        ("h", 60 * 60),
        ("m", 60),
        ("s", 1),
    ]
    time_str = ""
    for period, period_seconds in periods:
        if seconds >= period_seconds:
            time_value, seconds = divmod(seconds, period_seconds)
            time_str += f"{time_value}{period} "
    return time_str.strip()


async def get_readable_message(sid, is_user, page_no=1, status="All", page_step=1):
    msg = ""
    button = None

    tasks = await sync_to_async(get_specific_tasks, status, sid if is_user else None)

    STATUS_LIMIT = 4
    tasks_no = len(tasks)
    pages = (max(tasks_no, 1) + STATUS_LIMIT - 1) // STATUS_LIMIT
    if page_no > pages:
        page_no = (page_no - 1) % pages + 1
        status_dict[sid]["page_no"] = page_no
    elif page_no < 1:
        page_no = pages - (abs(page_no) % pages)
        status_dict[sid]["page_no"] = page_no
    start_position = (page_no - 1) * STATUS_LIMIT

    for index, task in enumerate(
        tasks[start_position : STATUS_LIMIT + start_position],
        start=1,
    ):
        tstatus = await sync_to_async(task.status) if status == "All" else status

        msg += f"<blockquote><b>🟢 {index + start_position}.{tstatus}:</b> <code>{escape(task.name())}</code></blockquote>\n"
        if task.listener.subname:
            msg += f"<i>{task.listener.subname}</i>\n"
        if (
            tstatus not in [MirrorStatus.STATUS_SEED, MirrorStatus.STATUS_QUEUEUP]
            and task.listener.progress
        ):
            progress = (
                await task.progress()
                if iscoroutinefunction(task.progress)
                else task.progress()
            )
            msg += f"{get_progress_bar_string(progress)} {progress}\n"
            subsize = f"/{get_readable_file_size(task.listener.subsize)}"
            msg += f"<b>Processed:</b> {task.processed_bytes()}{subsize}\n"
            msg += f"<b>Size:</b> {task.size()}\n"
            msg += f"<b>Speed:</b> {task.speed()}\n"
            msg += f"<b>ETA:</b> {task.eta()}\n"
        elif tstatus == MirrorStatus.STATUS_SEED:
            msg += f"<b>Seed Time:</b> {task.seeding_time()}\n"
        else:
            msg += f"<b>Size:</b> {task.size()}\n"
        msg += f"/stop_{task.gid()}\n\n"

    if len(msg) == 0:
        if status == "All":
            return None, None
        msg = f"<blockquote>🚫 No Active {status} Tasks!</blockquote>\n\n"

    buttons = ButtonMaker()
    if not is_user:
        buttons.data_button("📜 Overview", f"status {sid} ov", position="header")
    if len(tasks) > STATUS_LIMIT:
        msg += f"<b>Page:</b> {page_no}/{pages} | <b>Tasks:</b> {tasks_no} | <b>Step:</b> {page_step}\n"
        buttons.data_button("⬅️ Prev", f"status {sid} pre", position="header")
        buttons.data_button("➡️ Next", f"status {sid} nex", position="header")
        if tasks_no > 30:
            for i in [1, 2, 4, 6, 8, 10, 15]:
                buttons.data_button(
                    str(i),
                    f"status {sid} ps {i}",
                    position="footer",
                )
    if status != "All" or tasks_no > 20:
        for label, status_value in list(STATUSES.items()):
            if status_value != status:
                buttons.data_button(label, f"status {sid} st {status_value}")
    buttons.data_button("♻️ Refresh", f"status {sid} ref", position="header")
    button = buttons.build_menu(8)

    msg += f"<blockquote>💻 <b>CPU:</b> {cpu_percent()}% | 💾 <b>Free Space:</b> {get_readable_file_size(disk_usage(Config.DOWNLOAD_DIR).free)}</blockquote>\n"
    msg += f"<blockquote>🧠 <b>RAM:</b> {virtual_memory().percent}% | ⏳ <b>Uptime:</b> {get_readable_time(time() - bot_start_time)}</blockquote>"
    return msg, button
