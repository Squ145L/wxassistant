#!/usr/bin/env python
"""wxassistant 更新工具 — 检查 GitHub 最新版本并下载更新

用法:
    python update.py          # 检查+更新（GUI）
    python update.py --check  # 仅检查，输出到 stdout
"""

import tkinter as tk
from tkinter import ttk, messagebox
import os
import sys
import shutil
import tempfile
import zipfile
import threading
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

GITHUB_REPO = "Squ145L/wxassistant"
GITHUB_RAW = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main"
GITHUB_ZIP = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.zip"

APP_DIR = Path(__file__).parent.resolve()
VERSION_PATH = APP_DIR / "version.txt"

# 更新时跳过覆盖的文件/目录
SKIP_NAMES = {
    "cache", "logs", "__pycache__", ".git",
    "version.txt",  # 保留本地版本号（更新后覆盖为新的）
}

# 但 version.txt 应该被更新... 让我重新考虑。
# 实际上更新就是覆盖到最新版本，version.txt 也应该更新。
# 只跳过用户运行时数据。
SKIP_NAMES = {"cache", "logs", "__pycache__", ".git"}


# ================================================================
# 版本工具
# ================================================================

def parse_version(v: str) -> tuple:
    """'1.0.0' → (1, 0, 0)"""
    parts = v.strip().split(".")
    return tuple(int(p) for p in parts if p.isdigit())


def get_local_version() -> str:
    if VERSION_PATH.exists():
        return VERSION_PATH.read_text(encoding="utf-8").strip()
    return "0.0.0"


def get_remote_version() -> str:
    url = f"{GITHUB_RAW}/version.txt"
    req = Request(url, headers={"User-Agent": "wxassistant-updater"})
    with urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8").strip()


def check_update() -> tuple[str, str, bool]:
    """返回 (本地版本, 远程版本, 是否有更新)"""
    local = get_local_version()
    remote = get_remote_version()
    has_update = parse_version(remote) > parse_version(local)
    return local, remote, has_update


# ================================================================
# 更新窗口
# ================================================================

class UpdateWindow(tk.Toplevel):
    """更新窗口：检查 → 确认 → 下载进度 → 完成"""

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.title("wxassistant 更新")
        self.resizable(False, False)
        self.transient(parent)

        self._local_ver = get_local_version()
        self._remote_ver = ""
        self._download_thread = None

        self._build_ui()
        self._center(parent)

        # 自动开始检查
        self.after(300, self._start_check)

    def _build_ui(self):
        self._main = ttk.Frame(self, padding=20)
        self._main.pack(fill=tk.BOTH, expand=True)

        # 标题
        ttk.Label(self._main, text="wxassistant 更新",
                  font=("Microsoft YaHei", 12, "bold")).pack(pady=(0, 12))

        # 状态区
        self._status_label = ttk.Label(
            self._main, text="正在检查更新...",
            font=("Microsoft YaHei", 10), wraplength=380)
        self._status_label.pack(fill=tk.X, pady=(0, 8))

        # 版本信息
        self._version_frame = ttk.Frame(self._main)
        self._version_frame.pack(fill=tk.X, pady=(0, 12))

        self._label_local = ttk.Label(
            self._version_frame,
            text=f"当前版本：v{self._local_ver}", font=("", 10))
        self._label_remote = ttk.Label(
            self._version_frame, text="", font=("", 10))

        # 进度条
        self._progress_frame = ttk.Frame(self._main)
        self._progress_var = tk.DoubleVar(value=0)
        self._progress_bar = ttk.Progressbar(
            self._progress_frame, variable=self._progress_var,
            mode="determinate", length=380)
        self._progress_label = ttk.Label(
            self._progress_frame, text="", font=("", 9), foreground="gray")

        # 按钮区（ttk 风格与主界面一致）
        self._btn_frame = ttk.Frame(self._main)
        self._btn_frame.pack(fill=tk.X, pady=(16, 0))
        self._btn_close = ttk.Button(
            self._btn_frame, text="关闭", command=self.destroy)
        self._btn_close.pack(side=tk.RIGHT)
        self._btn_action = ttk.Button(
            self._btn_frame, text="检查更新", command=self._start_check)
        self._btn_action.pack(side=tk.RIGHT, padx=(0, 10))

    # ================================================================
    # 检查更新
    # ================================================================

    def _start_check(self):
        self._btn_action.config(state=tk.DISABLED, text="检查中...")
        self._status_label.config(text="正在连接 GitHub...")
        self._label_local.pack_forget()
        self._label_remote.pack_forget()

        def _check():
            try:
                remote = get_remote_version()
                has_update = parse_version(remote) > parse_version(self._local_ver)
                self.after(0, lambda: self._on_check_done(remote, has_update))
            except Exception as e:
                self.after(0, lambda: self._on_check_error(str(e)))

        threading.Thread(target=_check, daemon=True).start()

    def _on_check_done(self, remote: str, has_update: bool):
        self._remote_ver = remote
        self._btn_action.config(state=tk.NORMAL)

        self._label_local.config(text=f"当前版本：v{self._local_ver}")
        self._label_local.pack(anchor=tk.W)
        self._label_remote.config(text=f"最新版本：v{remote}")
        self._label_remote.pack(anchor=tk.W)

        if has_update:
            self._status_label.config(
                text=f"✨ 发现新版本 v{remote}！",
                foreground="#d35400")
            self._btn_action.config(text="立即更新", command=self._confirm_update)
        else:
            self._status_label.config(
                text="✅ 已是最新版本", foreground="#27ae60")
            self._btn_action.config(text="重新检查", command=self._start_check)

    def _on_check_error(self, error: str):
        self._status_label.config(
            text=f"❌ 检查失败\n{error}", foreground="red")
        self._label_local.pack(anchor=tk.W)
        self._btn_action.config(state=tk.NORMAL, text="重试",
                                command=self._start_check)

    # ================================================================
    # 确认 → 下载
    # ================================================================

    def _confirm_update(self):
        if not messagebox.askyesno(
            "确认更新",
            f"当前版本：v{self._local_ver}\n"
            f"最新版本：v{self._remote_ver}\n\n"
            f"更新将覆盖程序文件，保留 cache/ 和 logs/。\n"
            f"更新完成后需重启程序。\n\n"
            f"确认更新？",
            parent=self,
        ):
            return

        self._btn_action.config(state=tk.DISABLED, text="下载中...")
        self._btn_close.config(state=tk.DISABLED)
        self._status_label.config(
            text="正在下载更新...", foreground="black")

        # 显示进度条
        self._progress_frame.pack(fill=tk.X, pady=(0, 8))
        self._progress_var.set(0)
        self._progress_label.config(text="准备下载...")

        threading.Thread(target=self._do_update, daemon=True).start()

    def _do_update(self):
        try:
            # 1. 下载 zip
            self._update_progress(0, "正在下载...")

            tmp_dir = tempfile.mkdtemp(prefix="wxupdate_")
            zip_path = os.path.join(tmp_dir, "update.zip")

            self._download_with_progress(GITHUB_ZIP, zip_path)

            # 2. 解压
            self._update_progress(95, "正在解压...")
            extract_dir = os.path.join(tmp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            # GitHub zip 内部有一层 wxassistant-main/ 目录
            inner = os.path.join(extract_dir, "wxassistant-main")
            if not os.path.isdir(inner):
                # 尝试找第一个子目录
                dirs = [d for d in os.listdir(extract_dir)
                        if os.path.isdir(os.path.join(extract_dir, d))]
                if dirs:
                    inner = os.path.join(extract_dir, dirs[0])

            # 3. 覆盖文件
            self._update_progress(97, "正在安装...")
            self._replace_files(inner, str(APP_DIR))

            # 4. 清理
            shutil.rmtree(tmp_dir, ignore_errors=True)

            self.after(0, self._on_done)
        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)))

    def _download_with_progress(self, url: str, dest: str):
        """下载文件并更新进度条"""

        req = Request(url, headers={"User-Agent": "wxassistant-updater"})
        resp = urlopen(req, timeout=60)
        total = int(resp.headers.get("Content-Length", 0)) or -1

        downloaded = 0
        chunk_size = 8192

        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                if total > 0:
                    pct = int(downloaded / total * 90)  # 0-90% 给下载
                    mb_done = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    self._update_progress(
                        pct,
                        f"下载中... {mb_done:.1f}MB / {mb_total:.1f}MB" if mb_total < 50
                        else f"下载中... {mb_done:.1f}MB / {mb_total:.0f}MB",
                    )
                else:
                    mb = downloaded / (1024 * 1024)
                    self._update_progress(0, f"下载中... {mb:.1f}MB")

    def _replace_files(self, src_dir: str, dst_dir: str):
        """用新文件覆盖旧目录，跳过运行时数据"""
        for root, dirs, files in os.walk(src_dir):
            # 跳过特定目录
            dirs[:] = [d for d in dirs if d not in SKIP_NAMES]

            rel = os.path.relpath(root, src_dir)
            target_dir = os.path.join(dst_dir, rel) if rel != "." else dst_dir
            os.makedirs(target_dir, exist_ok=True)

            for fname in files:
                if fname in SKIP_NAMES:
                    continue
                src = os.path.join(root, fname)
                dst = os.path.join(target_dir, fname)
                shutil.copy2(src, dst)

    def _update_progress(self, value: float, text: str = ""):
        """线程安全更新进度（在主线程调用）"""
        def _set():
            self._progress_var.set(value)
            self._progress_label.config(text=text)

        if threading.current_thread() is threading.main_thread():
            _set()
        else:
            self.after(0, _set)

    # ================================================================
    # 完成 / 错误
    # ================================================================

    def _on_done(self):
        self._progress_var.set(100)
        self._progress_label.config(text="")
        self._status_label.config(
            text=f"✅ 更新完成！已更新到 v{self._remote_ver}\n请重启程序。",
            foreground="#27ae60")
        self._btn_action.config(
            state=tk.NORMAL, text="关闭", command=self.destroy)
        self._btn_close.pack_forget()

        messagebox.showinfo("更新完成",
                            f"已更新到 v{self._remote_ver}，请重启 wxassistant。",
                            parent=self)

    def _on_error(self, error: str):
        self._progress_frame.pack_forget()
        self._status_label.config(
            text=f"❌ 更新失败\n{error}", foreground="red")
        self._btn_action.config(
            state=tk.NORMAL, text="重试", command=self._confirm_update)
        self._btn_close.config(state=tk.NORMAL)

    # ================================================================
    # 工具
    # ================================================================

    def _center(self, parent: tk.Tk):
        w, h = 440, 300
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")


# ================================================================
# 入口
# ================================================================

def main():
    if "--check" in sys.argv:
        # 命令行模式：仅输出版本信息
        try:
            local, remote, has = check_update()
            print(f"local={local}")
            print(f"remote={remote}")
            print(f"update={'yes' if has else 'no'}")
        except Exception as e:
            print(f"error={e}", file=sys.stderr)
            sys.exit(1)
    else:
        # GUI 模式
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass

        # 先弹出一个小窗口显示状态
        win = UpdateWindow(root)
        win.grab_set()
        root.mainloop()


if __name__ == "__main__":
    main()
