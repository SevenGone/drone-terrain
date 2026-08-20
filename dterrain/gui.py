# -*- coding: utf-8 -*-
"""图形界面（双击即用）：选视频/航线 -> 填坐标 -> 一键识别地形地貌。"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import pipeline
from .categories import DEFAULT_CATEGORIES
from .config import CONFIG_PATH, Config
from .geo import build_track
from .report import save_results
from .srt import find_srt
from .video import probe

BACKENDS = ["features", "vision", "mock"]
BACKEND_LABEL = {
    "features": "本地特征 + DeepSeek 文本（默认）",
    "vision": "视觉大模型（直接看图）",
    "mock": "假结果（联调用，无需 Key）",
}
MODELS = ["deepseek-v4-flash", "deepseek-v4-pro"]


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("无人机航拍视频 → 坐标点位地形地貌识别（DeepSeek）")
        root.geometry("980x760")
        root.minsize(860, 640)

        self.q: "queue.Queue" = queue.Queue()
        self.running = False
        self.results = []
        self._thumbs = {}  # id -> PIL.ImageTk.PhotoImage

        self._build_vars()
        self._build_ui()
        self._load_settings()
        self._refresh_src_state()
        self._refresh_mode_state()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_queue)

    # ---------- 变量 ----------
    def _build_vars(self):
        self.video_var = tk.StringVar()
        self.src_var = tk.StringVar(value="route")  # route / srt
        self.route_var = tk.StringVar()
        self.srt_var = tk.StringVar()
        self.backend_var = tk.StringVar(value="features")
        self.mode_var = tk.StringVar(value="single")  # single / batch / sample
        self.lon_var = tk.StringVar()
        self.lat_var = tk.StringVar()
        self.coords_var = tk.StringVar()
        self.count_var = tk.IntVar(value=10)
        self.api_key_var = tk.StringVar()
        self.model_var = tk.StringVar(value="deepseek-v4-flash")
        self.api_base_var = tk.StringVar(value="https://api.deepseek.com")
        self.out_var = tk.StringVar(value=str(Path.cwd() / "out"))

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}
        root = self.root
        outer = ttk.Frame(root, padding=10)
        outer.pack(fill="both", expand=True)

        # 输入文件
        f1 = ttk.LabelFrame(outer, text="① 输入文件", padding=8)
        f1.pack(fill="x", pady=(0, 6))
        ttk.Label(f1, text="视频文件").grid(row=0, column=0, sticky="e", **pad)
        ttk.Entry(f1, textvariable=self.video_var, width=58).grid(row=0, column=1, sticky="we", **pad)
        ttk.Button(f1, text="浏览…", command=self._pick_video).grid(row=0, column=2, **pad)

        ttk.Radiobutton(f1, text="航线文件（CSV/GPX/KML，坐标来自航线图）", variable=self.src_var,
                        value="route", command=self._refresh_src_state).grid(row=1, column=0, sticky="e", **pad)
        self.route_entry = ttk.Entry(f1, textvariable=self.route_var, width=58)
        self.route_entry.grid(row=1, column=1, sticky="we", **pad)
        self.route_btn = ttk.Button(f1, text="浏览…", command=self._pick_route)
        self.route_btn.grid(row=1, column=2, **pad)

        ttk.Radiobutton(f1, text="大疆 SRT 字幕（视频内嵌 GPS）", variable=self.src_var,
                        value="srt", command=self._refresh_src_state).grid(row=2, column=0, sticky="e", **pad)
        self.srt_entry = ttk.Entry(f1, textvariable=self.srt_var, width=58)
        self.srt_entry.grid(row=2, column=1, sticky="we", **pad)
        self.srt_btn = ttk.Button(f1, text="浏览…", command=self._pick_srt)
        self.srt_btn.grid(row=2, column=2, **pad)
        ttk.Label(f1, text="", foreground="#777").grid(row=3, column=1, sticky="w")
        ttk.Label(f1, text="提示：无 GPS 时用航线文件（按匀速假设匹配）；视频建议从航线起点起飞时开始录",
                  foreground="#888").grid(row=3, column=1, sticky="w", padx=6)

        f1.columnconfigure(1, weight=1)

        # 识别方式 + 目标坐标
        f2 = ttk.LabelFrame(outer, text="② 识别方式与目标坐标", padding=8)
        f2.pack(fill="x", pady=(0, 6))
        ttk.Label(f2, text="识别后端").grid(row=0, column=0, sticky="e", **pad)
        self.backend_cb = ttk.Combobox(f2, textvariable=self.backend_var, values=BACKENDS,
                                       state="readonly", width=40)
        self.backend_cb.grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(f2, text=BACKEND_LABEL["features"], foreground="#888").grid(row=0, column=2, sticky="w", **pad)
        self.backend_cb.bind("<<ComboboxSelected>>", self._on_backend_change)

        ttk.Radiobutton(f2, text="单个坐标", variable=self.mode_var, value="single",
                        command=self._refresh_mode_state).grid(row=1, column=0, sticky="e", **pad)
        self.lon_entry = ttk.Entry(f2, textvariable=self.lon_var, width=16)
        self.lon_entry.grid(row=1, column=1, sticky="w", **pad)
        self.lat_entry = ttk.Entry(f2, textvariable=self.lat_var, width=16)
        self.lat_entry.grid(row=1, column=2, sticky="w", **pad)
        ttk.Label(f2, text="经度, 纬度（例：116.3281, 40.0755）", foreground="#888").grid(row=1, column=3, sticky="w", **pad)

        ttk.Radiobutton(f2, text="批量清单 CSV", variable=self.mode_var, value="batch",
                        command=self._refresh_mode_state).grid(row=2, column=0, sticky="e", **pad)
        self.coords_entry = ttk.Entry(f2, textvariable=self.coords_var, width=40)
        self.coords_entry.grid(row=2, column=1, columnspan=2, sticky="we", **pad)
        self.coords_btn = ttk.Button(f2, text="浏览…", command=self._pick_coords)
        self.coords_btn.grid(row=2, column=3, sticky="w", **pad)

        ttk.Radiobutton(f2, text="沿线采样", variable=self.mode_var, value="sample",
                        command=self._refresh_mode_state).grid(row=3, column=0, sticky="e", **pad)
        self.count_spin = ttk.Spinbox(f2, from_=2, to=500, textvariable=self.count_var, width=8)
        self.count_spin.grid(row=3, column=1, sticky="w", **pad)
        ttk.Label(f2, text="个点（沿航线均匀取点）", foreground="#888").grid(row=3, column=2, sticky="w", **pad)

        f2.columnconfigure(1, weight=1)

        # DeepSeek 配置
        f3 = ttk.LabelFrame(outer, text="③ DeepSeek 配置", padding=8)
        f3.pack(fill="x", pady=(0, 6))
        ttk.Label(f3, text="API Key").grid(row=0, column=0, sticky="e", **pad)
        ttk.Entry(f3, textvariable=self.api_key_var, width=44, show="*").grid(row=0, column=1, sticky="we", **pad)
        ttk.Label(f3, text="模型").grid(row=0, column=2, sticky="e", **pad)
        ttk.Combobox(f3, textvariable=self.model_var, values=MODELS, width=22).grid(row=0, column=3, sticky="we", **pad)
        ttk.Label(f3, text="API 地址").grid(row=1, column=0, sticky="e", **pad)
        ttk.Entry(f3, textvariable=self.api_base_var, width=44).grid(row=1, column=1, sticky="we", **pad)
        ttk.Label(f3, text="Key 在 platform.deepseek.com 获取（mock 后端可留空）", foreground="#888").grid(
            row=1, column=2, columnspan=2, sticky="w", **pad)
        f3.columnconfigure(1, weight=1)

        # 输出
        f4 = ttk.Frame(outer)
        f4.pack(fill="x", pady=(0, 6))
        ttk.Label(f4, text="输出目录").pack(side="left")
        ttk.Entry(f4, textvariable=self.out_var, width=58).pack(side="left", padx=6, fill="x", expand=True)
        ttk.Button(f4, text="浏览…", command=self._pick_out).pack(side="left", padx=2)

        # 运行按钮 + 进度
        f5 = ttk.Frame(outer)
        f5.pack(fill="x", pady=(0, 6))
        self.run_btn = ttk.Button(f5, text="▶ 开始识别", command=self._run)
        self.run_btn.pack(side="left")
        self.open_btn = ttk.Button(f5, text="打开结果目录", command=self._open_out, state="disabled")
        self.open_btn.pack(side="left", padx=8)
        self.progress = ttk.Progressbar(f5, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=8)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(f5, textvariable=self.status_var, foreground="#555").pack(side="right")

        # 结果区
        f6 = ttk.LabelFrame(outer, text="④ 结果", padding=6)
        f6.pack(fill="both", expand=True, pady=(0, 6))
        cols = ("id", "lon", "lat", "category", "confidence", "distance_m", "off")
        self.tree = ttk.Treeview(f6, columns=cols, show="headings", height=7)
        heads = {"id": "编号", "lon": "经度", "lat": "纬度", "category": "地貌",
                 "confidence": "置信度", "distance_m": "偏离(m)", "off": "偏离航线"}
        for c in cols:
            self.tree.heading(c, text=heads[c])
            w = 130 if c in ("lon", "lat") else (70 if c in ("confidence", "distance_m", "off") else 90)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # 缩略图预览
        prev = ttk.Frame(f6, width=320)
        prev.pack(side="right", fill="y", padx=(6, 0))
        ttk.Label(prev, text="帧截图预览").pack(anchor="w")
        self.thumb_label = ttk.Label(prev, anchor="center", text="（选中一行查看截图）", background="#eee")
        self.thumb_label.pack(fill="both", expand=True)
        self.reason_label = ttk.Label(prev, text="", wraplength=300, foreground="#555")
        self.reason_label.pack(fill="x", pady=(4, 0))

        # 日志
        f7 = ttk.LabelFrame(outer, text="日志", padding=4)
        f7.pack(fill="x")
        self.log_text = tk.Text(f7, height=5, state="disabled", wrap="word")
        self.log_text.pack(fill="x")
        sb = ttk.Scrollbar(f7, command=self.log_text.yview)
        sb.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=sb.set)

    # ---------- 状态刷新 ----------
    def _refresh_src_state(self):
        is_route = self.src_var.get() == "route"
        state = "normal" if is_route else "disabled"
        self.route_entry.config(state=state)
        self.route_btn.config(state=state)
        state2 = "disabled" if is_route else "normal"
        self.srt_entry.config(state=state2)
        self.srt_btn.config(state=state2)

    def _refresh_mode_state(self):
        m = self.mode_var.get()
        self.lon_entry.config(state="normal" if m == "single" else "disabled")
        self.lat_entry.config(state="normal" if m == "single" else "disabled")
        self.coords_entry.config(state="normal" if m == "batch" else "disabled")
        self.coords_btn.config(state="normal" if m == "batch" else "disabled")
        self.count_spin.config(state="normal" if m == "sample" else "disabled")

    def _on_backend_change(self, _e=None):
        self.status_var.set(BACKEND_LABEL.get(self.backend_var.get(), ""))

    # ---------- 文件选择 ----------
    def _pick_video(self):
        p = filedialog.askopenfilename(title="选择视频", filetypes=[("视频", "*.mp4 *.mov *.avi *.mkv"), ("所有文件", "*.*")])
        if p:
            self.video_var.set(p)
            if not self.srt_var.get():
                s = find_srt(p)
                if s:
                    self.srt_var.set(s)

    def _pick_route(self):
        p = filedialog.askopenfilename(title="选择航线文件", filetypes=[("航线", "*.csv *.gpx *.kml"), ("所有文件", "*.*")])
        if p:
            self.route_var.set(p)

    def _pick_srt(self):
        p = filedialog.askopenfilename(title="选择 SRT 字幕", filetypes=[("SRT", "*.srt"), ("所有文件", "*.*")])
        if p:
            self.srt_var.set(p)

    def _pick_coords(self):
        p = filedialog.askopenfilename(title="选择坐标清单", filetypes=[("CSV", "*.csv"), ("所有文件", "*.*")])
        if p:
            self.coords_var.set(p)

    def _pick_out(self):
        p = filedialog.askdirectory(title="选择输出目录")
        if p:
            self.out_var.set(p)

    def _open_out(self):
        d = self.out_var.get()
        try:
            if os.name == "nt":
                os.startfile(d)  # type: ignore[attr-defined]
            elif sys_platform() == "darwin":
                subprocess.run(["open", d])
            else:
                subprocess.run(["xdg-open", d])
        except Exception as e:
            messagebox.showerror("打开失败", str(e))

    # ---------- 设置持久化 ----------
    def _load_settings(self):
        data = {}
        try:
            if CONFIG_PATH.exists():
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        self.api_key_var.set(data.get("api_key", "") or os.environ.get("DTERRAIN_API_KEY", ""))
        self.model_var.set(data.get("model", "deepseek-v4-flash"))
        self.api_base_var.set(data.get("api_base", "https://api.deepseek.com"))
        self.backend_var.set(data.get("backend", "features"))

    def _save_settings(self):
        data = {
            "api_key": self.api_key_var.get(),
            "model": self.model_var.get(),
            "api_base": self.api_base_var.get(),
            "backend": self.backend_var.get(),
        }
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _on_close(self):
        self._save_settings()
        self.root.destroy()

    # ---------- 运行 ----------
    def _run(self):
        if self.running:
            return
        video = self.video_var.get().strip()
        if not video or not Path(video).exists():
            messagebox.showerror("提示", "请先选择视频文件")
            return

        src = self.src_var.get()
        route = self.route_var.get().strip() if src == "route" else ""
        srt = self.srt_var.get().strip() if src == "srt" else ""
        if src == "route" and not route:
            messagebox.showerror("提示", "请选择航线坐标文件（CSV/GPX/KML）")
            return

        mode = self.mode_var.get()
        if mode == "single":
            try:
                lon = float(self.lon_var.get().strip())
                lat = float(self.lat_var.get().strip())
                assert -180 <= lon <= 180 and -90 <= lat <= 90
                points = [("single", lat, lon)]
            except Exception:
                messagebox.showerror("提示", "请输入正确的经度/纬度（经度 -180~180，纬度 -90~90）")
                return
        elif mode == "batch":
            if not self.coords_var.get().strip():
                messagebox.showerror("提示", "请选择坐标清单 CSV")
                return
            points = None  # 由 worker 读取
        else:
            points = None

        backend = self.backend_var.get()
        if backend != "mock" and not self.api_key_var.get().strip():
            messagebox.showerror("提示", "识别后端非 mock，请填写 DeepSeek API Key")
            return

        self._save_settings()
        self.results = []
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._log_clear()
        self._log("开始…")
        self.status_var.set("运行中")
        self.run_btn.config(state="disabled")
        self.open_btn.config(state="disabled")
        self.progress.config(value=0)
        self.running = True

        args = dict(video=video, route=route, srt=srt, backend=backend,
                    api_key=self.api_key_var.get().strip(), model=self.model_var.get().strip(),
                    api_base=self.api_base_var.get().strip(), mode=mode, points=points,
                    coords_file=self.coords_var.get().strip(), count=int(self.count_var.get()),
                    out_dir=self.out_var.get().strip() or ".")
        threading.Thread(target=self._worker, args=(args,), daemon=True).start()

    def _worker(self, a: dict):
        try:
            self.q.put(("log", "读取视频信息…"))
            info = probe(a["video"])
            duration = float(info.get("duration") or 0)
            if duration <= 0:
                raise RuntimeError("视频时长读取为 0")
            self.q.put(("log", f"视频时长 {duration:.1f}s，分辨率 {info.get('width')}x{info.get('height')}"))

            self.q.put(("log", "构建坐标轨迹…"))
            track, aligned_by = build_track(a["srt"] or None, a["route"] or None, duration, 0.0)
            self.q.put(("log", f"轨迹点数 {len(track)}，对齐方式 {aligned_by}"))

            if a["points"] is None:
                if a["mode"] == "batch":
                    points = pipeline.read_coords_csv(a["coords_file"])
                else:
                    points = pipeline.sample_points(track, duration, None, a["count"])
            else:
                points = a["points"]

            cfg = Config(backend=a["backend"], api_base=a["api_base"], model=a["model"],
                         api_key=a["api_key"], categories=list(DEFAULT_CATEGORIES),
                         max_dist_meters=200.0, timeout=60.0, retries=3, max_side=1024)

            self.q.put(("log", f"开始识别 {len(points)} 个点位（后端 {a['backend']}）…"))

            def progress(done, total, pid):
                self.q.put(("progress", done, total, pid))

            results = pipeline.run_points(a["video"], duration, track, cfg, a["out_dir"],
                                          points, aligned_by, progress=progress)
            jp, cp = save_results(results, a["out_dir"])
            self.q.put(("log", f"完成！结果已保存：{jp} / {cp}"))
            self.q.put(("done", results))
        except Exception as e:
            self.q.put(("error", str(e)))

    def _poll_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log(msg[1])
                elif kind == "progress":
                    _, done, total, pid = msg
                    self.progress.config(maximum=total, value=done)
                    self.status_var.set(f"处理中 {done}/{total}：{pid}")
                elif kind == "done":
                    self.results = msg[1]
                    self._populate_tree(msg[1])
                    self.status_var.set(f"完成 {len(msg[1])} 个点位")
                    self._finish()
                elif kind == "error":
                    self._log("错误：" + msg[1])
                    self.status_var.set("失败")
                    messagebox.showerror("出错了", msg[1])
                    self._finish()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _finish(self):
        self.running = False
        self.run_btn.config(state="normal")
        self.open_btn.config(state="normal")

    def _populate_tree(self, results):
        for r in results:
            conf = f"{r['confidence']:.2f}" if r.get("confidence") is not None else "-"
            self.tree.insert("", "end", iid=r["id"], values=(
                r["id"], r["lon"], r["lat"], r["category"], conf,
                r["distance_m"], "是" if r["off_route"] else "否"))
            self._thumbs[r["id"]] = r["frame_path"]

    def _on_select(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        frame = self._thumbs.get(iid)
        if frame:
            self._show_thumb(frame)
        # 显示依据
        for r in self.results:
            if str(r["id"]) == iid:
                self.reason_label.config(text="依据：" + (r.get("reason") or ""))
                break

    def _show_thumb(self, path):
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            img.thumbnail((320, 260))
            photo = ImageTk.PhotoImage(img)
            self.thumb_label.config(image=photo, text="")
            self.thumb_label.image = photo
        except Exception as e:
            self.thumb_label.config(image="", text=f"无法预览：{e}")

    # ---------- 日志 ----------
    def _log(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _log_clear(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")


def sys_platform() -> str:
    import sys
    return sys.platform


def main():
    try:
        root = tk.Tk()
        App(root)
        root.mainloop()
    except Exception as e:
        # 无显示环境时的兜底提示
        try:
            messagebox.showerror("启动失败", str(e))
        except Exception:
            print(f"[错误] {e}")


if __name__ == "__main__":
    main()
