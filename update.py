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
import subprocess
import tempfile
import time
import zipfile
import threading
from pathlib import Path
from urllib.request import urlopen, Request

GITHUB_REPO = "Squ145L/wxassistant"
GITHUB_RAW = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main"
GITHUB_ZIP = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.zip"

APP_DIR = Path(__file__).parent.resolve()
VERSION_PATH = APP_DIR / "version.txt"

SKIP_NAMES = {"cache", "logs", "__pycache__", ".git"}


# ================================================================
# 版本工具
# ================================================================

def parse_version(v: str) -> tuple:
    """'1.0.0' → (1, 0, 0)"""
    v = v.strip().lstrip("﻿").strip()
    parts = v.split(".")
    nums = []
    for p in parts:
        p = p.strip().lstrip("﻿")
        if not p:
            continue
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    return tuple(nums) if nums else (0,)


def get_local_version() -> str:
    if VERSION_PATH.exists():
        return VERSION_PATH.read_text(encoding="utf-8").lstrip("﻿").strip()
    return "0.0.0"


def get_remote_version() -> str:
    url = f"{GITHUB_RAW}/version.txt"
    req = Request(url, headers={"User-Agent": "wxassistant-updater"})
    with urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8").lstrip("﻿").strip()


def check_update() -> tuple[str, str, bool]:
    local = get_local_version()
    remote = get_remote_version()
    has_update = parse_version(remote) > parse_version(local)
    return local, remote, has_update


# ================================================================
# 更新窗口
# ================================================================

class UpdateWindow(tk.Tk):
    """更新窗口：检查 → 确认 → 下载进度 → 完成"""

    def __init__(self):
        super().__init__()
        self.title("wxassistant 更新")
        self.resizable(False, False)

        self._local_ver = get_local_version()
        self._remote_ver = ""

        self._build_ui()
        self._center()

        self.after(300, self._start_check)

    def _build_ui(self):
        self._main = ttk.Frame(self, padding=20)
        self._main.pack(fill=tk.BOTH, expand=True)

        # 标题
        ttk.Label(self._main, text="wxassistant 更新",
                  font=("Microsoft YaHei", 12, "bold")).pack(pady=(0, 12))

        # 状态
        self._status_label = ttk.Label(
            self._main, text="正在检查更新...",
            font=("Microsoft YaHei", 10), wraplength=380)
        self._status_label.pack(fill=tk.X, pady=(0, 8))

        # 版本信息
        self._version_frame = ttk.Frame(self._main)
        self._version_frame.pack(fill=tk.X, pady=(0, 8))

        self._label_local = ttk.Label(
            self._version_frame, text=f"当前版本：v{self._local_ver}", font=("", 10))
        self._label_remote = ttk.Label(
            self._version_frame, text="", font=("", 10))

        # 进度区域（初始隐藏）
        self._progress_frame = ttk.Frame(self._main)

        self._progress_var = tk.DoubleVar(value=0)
        self._progress_bar = ttk.Progressbar(
            self._progress_frame, variable=self._progress_var,
            mode="determinate", length=380)
        self._progress_bar.pack(fill=tk.X, pady=(0, 4))

        # 进度文字（速度 + 百分比）
        self._progress_label = ttk.Label(
            self._progress_frame, text="", font=("", 9), foreground="gray")
        self._progress_label.pack(anchor=tk.W)

        # 当前文件/操作详情
        self._detail_label = ttk.Label(
            self._progress_frame, text="", font=("", 9), foreground="#555")
        self._detail_label.pack(anchor=tk.W)

        # 日志区：滚动显示最近操作
        log_frame = ttk.Frame(self._progress_frame)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self._log_text = tk.Text(
            log_frame, height=5, width=52, font=("Consolas", 8),
            state=tk.DISABLED, bg="#f8f8f8", relief=tk.FLAT,
            borderwidth=1, padx=6, pady=4)
        self._log_text.pack(fill=tk.BOTH, expand=True)

        # 按钮区
        self._btn_frame = ttk.Frame(self._main)
        self._btn_frame.pack(fill=tk.X, pady=(12, 0))
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
        self._progress_frame.pack_forget()

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

        self._btn_action.pack_forget()
        self._btn_close.config(state=tk.DISABLED)

        # 隐藏版本信息，显示进度区
        self._label_local.pack_forget()
        self._label_remote.pack_forget()
        self._status_label.config(
            text="正在下载更新...", foreground="black")

        self._progress_frame.pack(fill=tk.X, pady=(0, 8))
        self._progress_var.set(0)
        self._progress_label.config(text="准备中...")
        self._detail_label.config(text="")
        self._clear_log()

        threading.Thread(target=self._do_update, daemon=True).start()

    def _do_update(self):
        try:
            # 1. 下载
            self._log("⬇ 开始下载主程序包...")
            tmp_dir = tempfile.mkdtemp(prefix="wxupdate_")
            zip_path = os.path.join(tmp_dir, "update.zip")
            self._download_with_progress(GITHUB_ZIP, zip_path)

            # 2. 解压
            self._update_progress(90, "正在解压...")
            self._log("📦 正在解压...")
            extract_dir = os.path.join(tmp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                file_list = [n for n in zf.namelist() if not n.endswith("/")]
                total_files = len(file_list)
                for i, name in enumerate(file_list):
                    zf.extract(name, extract_dir)
                    if i % 8 == 0 or i == total_files - 1:
                        self._update_progress(
                            90 + int((i + 1) / total_files * 5),
                            f"解压中... {i + 1}/{total_files}")
                        display = name.split("/", 1)[-1] if "/" in name else name
                        self._detail(f"  {display}")
            self._log(f"  解压完成 ({total_files} 个文件)")

            # 3. 找内部目录
            inner = os.path.join(extract_dir, "wxassistant-main")
            if not os.path.isdir(inner):
                dirs = [d for d in os.listdir(extract_dir)
                        if os.path.isdir(os.path.join(extract_dir, d))]
                if dirs:
                    inner = os.path.join(extract_dir, dirs[0])

            # 4. 覆盖安装
            self._update_progress(95, "正在安装...")
            self._log("📋 正在安装文件...")
            self._replace_files(inner, str(APP_DIR))

            # 5. 清理
            shutil.rmtree(tmp_dir, ignore_errors=True)

            self.after(0, self._on_done)
        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)))

    def _download_with_progress(self, url: str, dest: str):
        req = Request(url, headers={"User-Agent": "wxassistant-updater"})
        resp = urlopen(req, timeout=120)
        total = int(resp.headers.get("Content-Length", 0)) or -1

        downloaded = 0
        chunk_size = 65536
        start_time = time.time()
        last_update = start_time

        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                now = time.time()
                if now - last_update < 0.15 and downloaded < total:
                    continue  # 限制 UI 更新频率
                last_update = now

                elapsed = now - start_time
                speed = downloaded / elapsed if elapsed > 0 else 0

                if total > 0:
                    pct = int(downloaded / total * 90)
                    mb_done = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    # 速度格式化
                    if speed > 1024 * 1024:
                        speed_str = f"{speed / (1024 * 1024):.1f} MB/s"
                    else:
                        speed_str = f"{speed / 1024:.0f} KB/s"
                    self._update_progress(
                        pct, f"下载中... {mb_done:.1f} / {mb_total:.1f} MB  ({speed_str})")
                else:
                    mb = downloaded / (1024 * 1024)
                    self._update_progress(0, f"下载中... {mb:.1f} MB  (大小未知)")

    def _replace_files(self, src_dir: str, dst_dir: str):
        # 收集所有文件
        all_files = []
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_NAMES]
            for fname in files:
                if fname not in SKIP_NAMES:
                    rel = os.path.relpath(os.path.join(root, fname), src_dir)
                    all_files.append(rel)

        total = len(all_files)
        for i, rel in enumerate(all_files):
            src = os.path.join(src_dir, rel)
            dst = os.path.join(dst_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

            if i % 5 == 0 or i == total - 1:
                pct = 95 + int((i + 1) / total * 5)
                self._update_progress(pct, f"安装中... {i + 1}/{total}")
                self._detail(f"  {rel}")

        self._log(f"  安装完成 ({total} 个文件)")

    # ================================================================
    # 线程安全 UI 更新
    # ================================================================

    def _update_progress(self, value: float, text: str = ""):
        def _set():
            self._progress_var.set(value)
            self._progress_label.config(text=text)
        self._safe(_set)

    def _detail(self, text: str):
        def _set():
            self._detail_label.config(text=text)
        self._safe(_set)

    def _log(self, text: str):
        def _set():
            self._log_text.config(state=tk.NORMAL)
            self._log_text.insert(tk.END, text + "\n")
            self._log_text.see(tk.END)
            self._log_text.config(state=tk.DISABLED)
        self._safe(_set)

    def _clear_log(self):
        def _set():
            self._log_text.config(state=tk.NORMAL)
            self._log_text.delete("1.0", tk.END)
            self._log_text.config(state=tk.DISABLED)
        self._safe(_set)

    def _safe(self, fn):
        if threading.current_thread() is threading.main_thread():
            fn()
        else:
            self.after(0, fn)

    # ================================================================
    # 完成 / 错误
    # ================================================================

    def _on_done(self):
        self._progress_var.set(100)
        self._progress_label.config(text="全部完成！")
        self._detail_label.config(text="")
        self._log("✅ 更新完成！请重启程序以使用新版本。")
        self._status_label.config(
            text=f"✅ 已更新到 v{self._remote_ver}",
            foreground="#27ae60")

        # 按钮：重启 + 关闭
        self._btn_close.config(state=tk.NORMAL, text="关闭")
        self._btn_action.config(
            state=tk.NORMAL, text="🔄 重启程序",
            command=self._restart_app)
        self._btn_action.pack(side=tk.RIGHT, padx=(0, 10))

    def _on_error(self, error: str):
        self._log(f"❌ 更新失败: {error}")
        self._status_label.config(
            text=f"❌ 更新失败\n{error}", foreground="red")
        self._btn_action.config(
            state=tk.NORMAL, text="重试", command=self._confirm_update)
        self._btn_action.pack(side=tk.RIGHT, padx=(0, 10))
        self._btn_close.config(state=tk.NORMAL)

    def _restart_app(self):
        """重启 wxassistant 主程序"""
        main_py = APP_DIR / "main.py"
        if main_py.exists():
            subprocess.Popen(
                [sys.executable, str(main_py)],
                cwd=str(APP_DIR),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        self.destroy()

    # ================================================================
    # 工具
    # ================================================================

    def _center(self):
        w, h = 460, 420
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")


# ================================================================
# 入口
# ================================================================

def main():
    if "--check" in sys.argv:
        try:
            local, remote, has = check_update()
            print(f"local={local}")
            print(f"remote={remote}")
            print(f"update={'yes' if has else 'no'}")
        except Exception as e:
            print(f"error={e}", file=sys.stderr)
            sys.exit(1)
    else:
        win = UpdateWindow()
        win.mainloop()


if __name__ == "__main__":
    main()
