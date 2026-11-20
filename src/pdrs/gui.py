"""Tkinter desktop interface for the read-only PDRS carving prototype."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

from pdrs.carve import carve_image
from pdrs.evaluation import EvaluationResult, GroundTruthRecord, evaluate_ground_truth, load_ground_truth, write_evaluation
from pdrs.manifest import write_manifest
from pdrs.reporting import build_experiment_report, write_new_report
from pdrs.structure import ImageStructure, format_report, inspect_image, report_json


class PDRSApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PDRS | 数据恢复实验工具")
        self.root.geometry("1040x840")
        self.root.minsize(900, 700)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        self.image_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.ground_truth_path = tk.StringVar()
        self.status = tk.StringVar(value="请选择 raw 镜像和一个空的输出目录。")
        self.file_info = tk.StringVar(value="尚未选择镜像")
        self.result_info = tk.StringVar(value="尚未运行扫描")
        self.summary_info = tk.StringVar(value="扫描结束后会显示候选数、边界完整性和格式校验统计。")
        self.evaluation_info = tk.StringVar(value="")
        self.manifest_info = tk.StringVar(value="")
        self.details = tk.StringVar(value="选择一条候选记录以查看完整校验信息。")
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._busy = False
        self._rows_by_filename: dict[str, dict[str, object]] = {}
        self._last_output_dir: Path | None = None
        self._last_report_context: tuple[
            Path,
            list[dict[str, object]],
            EvaluationResult | None,
            datetime,
            datetime,
            tuple[int, int],
        ] | None = None
        self._ground_truth_status: dict[str, str] = {}
        self._has_ground_truth_evaluation = False

        self._configure_style()
        self._build_layout()
        self.root.after(100, self._poll_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("PageTitle.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("SubTitle.TLabel", font=("Segoe UI", 10), foreground="#52606d")
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Run.TButton", font=("Segoe UI", 10, "bold"), padding=(16, 8))
        style.configure("Treeview", rowheight=27)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _build_layout(self) -> None:
        page = ttk.Frame(self.root, padding=(22, 18))
        page.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(3, weight=1)

        ttk.Label(page, text="PDRS 数据恢复实验工具", style="PageTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            page,
            text="对用户选择的 raw 镜像执行只读扫描，候选文件和 manifest 写入单独目录。",
            style="SubTitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 18))

        form = ttk.LabelFrame(page, text="扫描设置", padding=14)
        form.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="镜像文件").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=5)
        self.image_entry = ttk.Entry(form, textvariable=self.image_path)
        self.image_entry.grid(row=0, column=1, sticky="ew", pady=5)
        self.image_entry.bind(
            "<Control-v>", lambda _event: self._paste_path(self.image_entry, refresh_image_info=True)
        )
        self.image_paste_button = ttk.Button(
            form, text="粘贴", command=lambda: self._paste_path(self.image_entry, refresh_image_info=True)
        )
        self.image_paste_button.grid(row=0, column=2, padx=(8, 0), pady=5)
        self.image_button = ttk.Button(form, text="浏览…", command=self._choose_image)
        self.image_button.grid(row=0, column=3, padx=(8, 0), pady=5)
        ttk.Label(form, textvariable=self.file_info, style="SubTitle.TLabel").grid(
            row=1, column=1, sticky="w", pady=(0, 6)
        )

        ttk.Label(form, text="输出目录").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=5)
        self.output_entry = ttk.Entry(form, textvariable=self.output_path)
        self.output_entry.grid(row=2, column=1, sticky="ew", pady=5)
        self.output_entry.bind("<Control-v>", lambda _event: self._paste_path(self.output_entry))
        self.output_paste_button = ttk.Button(
            form, text="粘贴", command=lambda: self._paste_path(self.output_entry)
        )
        self.output_paste_button.grid(row=2, column=2, padx=(8, 0), pady=5)
        self.output_button = ttk.Button(form, text="浏览…", command=self._choose_output)
        self.output_button.grid(row=2, column=3, padx=(8, 0), pady=5)
        ttk.Label(
            form,
            text="可直接粘贴路径；目录不存在时自动创建，已有目录必须为空。",
            style="SubTitle.TLabel",
        ).grid(row=3, column=1, sticky="w", pady=(0, 6))

        ttk.Label(form, text="Ground truth（可选）").grid(
            row=4, column=0, sticky="w", padx=(0, 12), pady=5
        )
        self.ground_truth_entry = ttk.Entry(form, textvariable=self.ground_truth_path)
        self.ground_truth_entry.grid(row=4, column=1, sticky="ew", pady=5)
        self.ground_truth_entry.bind(
            "<Control-v>", lambda _event: self._paste_path(self.ground_truth_entry)
        )
        self.ground_truth_paste_button = ttk.Button(
            form, text="粘贴", command=lambda: self._paste_path(self.ground_truth_entry)
        )
        self.ground_truth_paste_button.grid(row=4, column=2, padx=(8, 0), pady=5)
        self.ground_truth_button = ttk.Button(
            form, text="浏览…", command=self._choose_ground_truth
        )
        self.ground_truth_button.grid(row=4, column=3, padx=(8, 0), pady=5)
        ttk.Label(
            form,
            text="选择实验集的 ground_truth.csv，可自动对照 SHA-256 和预期偏移。",
            style="SubTitle.TLabel",
        ).grid(row=5, column=1, sticky="w", pady=(0, 6))

        actions = ttk.Frame(form)
        actions.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.run_button = ttk.Button(
            actions, text="开始只读扫描", style="Run.TButton", command=self._start_scan
        )
        self.run_button.grid(row=0, column=0, sticky="w")
        self.inspect_button = ttk.Button(
            actions, text="查看镜像结构", command=self._inspect_structure
        )
        self.inspect_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=200)
        self.progress.grid(row=0, column=2, sticky="ew", padx=(16, 12))
        ttk.Label(actions, textvariable=self.status, anchor="w").grid(row=0, column=3, sticky="e")
        actions.columnconfigure(2, weight=1)

        results = ttk.LabelFrame(page, text="扫描结果", padding=12)
        results.grid(row=3, column=0, sticky="nsew")
        results.columnconfigure(0, weight=1)
        results.rowconfigure(3, weight=1)
        result_header = ttk.Frame(results)
        result_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(result_header, textvariable=self.result_info, style="Section.TLabel").pack(side="left")
        ttk.Label(result_header, textvariable=self.manifest_info, style="SubTitle.TLabel").pack(side="right")
        ttk.Label(results, textvariable=self.summary_info, style="SubTitle.TLabel").grid(
            row=1, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Label(results, textvariable=self.evaluation_info, style="SubTitle.TLabel").grid(
            row=2, column=0, sticky="w", pady=(0, 8)
        )

        table_frame = ttk.Frame(results)
        table_frame.grid(row=3, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("filename", "format", "offset", "size", "boundary", "valid")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "filename": ("候选文件", 310),
            "format": ("格式", 75),
            "offset": ("镜像偏移", 115),
            "size": ("字节数", 100),
            "boundary": ("边界", 100),
            "valid": ("格式校验", 110),
        }
        for column, (title, width) in headings.items():
            self.table.heading(column, text=title)
            self.table.column(column, width=width, minwidth=65, anchor="w")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.table.bind("<<TreeviewSelect>>", self._show_selected_details)

        detail_frame = ttk.LabelFrame(results, text="候选详情", padding=(10, 7))
        detail_frame.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        detail_frame.columnconfigure(0, weight=1)
        ttk.Label(detail_frame, textvariable=self.details, justify="left", wraplength=740).grid(
            row=0, column=0, sticky="ew"
        )
        detail_actions = ttk.Frame(detail_frame)
        detail_actions.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.copy_sha_button = ttk.Button(
            detail_actions, text="复制 SHA-256", command=self._copy_selected_sha256, state="disabled"
        )
        self.copy_sha_button.pack(fill="x")
        self.open_output_button = ttk.Button(
            detail_actions, text="打开结果目录", command=self._open_output_dir, state="disabled"
        )
        self.open_output_button.pack(fill="x", pady=(5, 0))
        self.export_report_button = ttk.Button(
            detail_actions,
            text="导出实验报告",
            command=self._export_experiment_report,
            state="disabled",
        )
        self.export_report_button.pack(fill="x", pady=(5, 0))

        ttk.Label(
            page,
            text="支持 BMP、JPEG、PNG、PDF、SQLite 连续文件雕刻；可查看 MBR/GPT、FAT32、exFAT 与 ext 卷元数据。不会遍历目录、恢复删除记录或重组碎片文件。",
            style="SubTitle.TLabel",
            wraplength=980,
        ).grid(row=4, column=0, sticky="w", pady=(12, 0))

    def _choose_image(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="选择 raw 镜像文件",
            filetypes=(("Raw 镜像", "*.img *.raw *.dd *.bin"), ("所有文件", "*.*")),
        )
        if selected:
            self.image_path.set(selected)
            self._refresh_file_info()

    def _inspect_structure(self) -> None:
        if self._busy:
            return
        source = Path(self.image_path.get().strip()).expanduser()
        if not source.is_file():
            messagebox.showerror("镜像无效", "请选择一个存在的常规镜像文件。", parent=self.root)
            return
        try:
            report = inspect_image(source)
        except (OSError, ValueError) as error:
            messagebox.showerror("结构读取失败", str(error), parent=self.root)
            return
        self.status.set("镜像结构已读取（只读）")

        window = tk.Toplevel(self.root)
        window.title("PDRS | 镜像结构只读摘要")
        window.geometry("780x640")
        window.minsize(620, 420)
        window.transient(self.root)
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        output = ScrolledText(body, wrap="word", font=("Consolas", 10))
        output.grid(row=0, column=0, sticky="nsew")
        report_text = format_report(report)
        output.insert("1.0", report_text)
        output.configure(state="disabled")
        actions = ttk.Frame(body)
        actions.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(
            actions,
            text="复制摘要",
            command=lambda: self._copy_structure_report(report_text),
        ).pack(side="left")
        ttk.Button(
            actions,
            text="保存 JSON…",
            command=lambda: self._save_structure_report(report),
        ).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="关闭", command=window.destroy).pack(side="right")

    def _copy_structure_report(self, report_text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(report_text)
        self.status.set("镜像结构摘要已复制")

    def _save_structure_report(self, report: ImageStructure) -> None:
        source_name = Path(self.image_path.get().strip()).stem or "image"
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title="保存镜像结构 JSON",
            initialfile=f"{source_name}_structure.json",
            defaultextension=".json",
            filetypes=(("JSON 文件", "*.json"), ("所有文件", "*.*")),
        )
        if not selected:
            return
        target = Path(selected).expanduser()
        try:
            with target.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(report_json(report))
                handle.write("\n")
        except FileExistsError:
            messagebox.showerror(
                "文件已存在", "为避免覆盖已有报告，请选择一个新文件名。", parent=self.root
            )
            return
        except OSError as error:
            messagebox.showerror("保存失败", str(error), parent=self.root)
            return
        self.status.set(f"结构报告已保存：{target}")

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(parent=self.root, title="选择输出目录", mustexist=False)
        if selected:
            self.output_path.set(selected)

    def _choose_ground_truth(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="选择 ground_truth.csv",
            filetypes=(("CSV 文件", "*.csv"), ("所有文件", "*.*")),
        )
        if selected:
            self.ground_truth_path.set(selected)

    def _paste_path(self, entry: ttk.Entry, *, refresh_image_info: bool = False) -> str:
        try:
            value = self.root.clipboard_get().strip()
        except tk.TclError:
            messagebox.showinfo("剪贴板为空", "请先复制一个文件或文件夹路径，再粘贴。", parent=self.root)
            return "break"
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if not value:
            messagebox.showinfo("剪贴板为空", "请先复制一个文件或文件夹路径，再粘贴。", parent=self.root)
            return "break"
        entry.delete(0, tk.END)
        entry.insert(0, value)
        if refresh_image_info:
            self._refresh_file_info()
        return "break"

    def _refresh_file_info(self) -> None:
        path = Path(self.image_path.get()).expanduser()
        try:
            size = path.stat().st_size
        except OSError:
            self.file_info.set("找不到文件或无法读取文件信息")
            return
        self.file_info.set(f"大小：{self._format_size(size)}")

    @staticmethod
    def _format_size(size: int) -> str:
        value = float(size)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if value < 1024 or unit == "TiB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{size:,} B"
            value /= 1024
        return f"{size:,} B"

    @staticmethod
    def _format_valid(value: object) -> str:
        if value is True:
            return "有效"
        if value is False:
            return "未通过"
        return "未检查"

    def _start_scan(self) -> None:
        if self._busy:
            return
        image_text = self.image_path.get().strip()
        output_text = self.output_path.get().strip()
        source = Path(image_text).expanduser()
        output = Path(output_text).expanduser()
        if not source.is_file():
            messagebox.showerror("镜像无效", "请选择一个存在的常规镜像文件。", parent=self.root)
            return
        if not output_text:
            messagebox.showerror("缺少输出目录", "请选择候选文件的输出目录。", parent=self.root)
            return
        try:
            source_resolved = source.resolve(strict=True)
            output_resolved = output.resolve()
            if output_resolved == source_resolved.parent:
                raise ValueError("输出目录不能是镜像文件所在目录。")
            if output.exists() and not output.is_dir():
                raise ValueError("输出路径已存在，但不是目录。")
            if output.exists() and any(output.iterdir()):
                raise ValueError("输出目录必须为空，请选择一个新的空目录。")
        except (OSError, ValueError) as error:
            messagebox.showerror("输出目录不可用", str(error), parent=self.root)
            return

        ground_truth_records: list[GroundTruthRecord] | None = None
        ground_truth_text = self.ground_truth_path.get().strip()
        if ground_truth_text:
            ground_truth_file = Path(ground_truth_text).expanduser()
            if not ground_truth_file.is_file():
                messagebox.showerror("Ground truth 无效", "请选择一个存在的 CSV 文件。", parent=self.root)
                return
            try:
                ground_truth_records = load_ground_truth(ground_truth_file, source.name)
            except ValueError as error:
                messagebox.showerror("Ground truth 无法使用", str(error), parent=self.root)
                return

        try:
            source_stat = source.stat()
        except OSError as error:
            messagebox.showerror("镜像不可用", str(error), parent=self.root)
            return
        source_signature = (source_stat.st_size, source_stat.st_mtime_ns)
        scan_started_at = datetime.now().astimezone()
        self._last_report_context = None
        self.export_report_button.configure(state="disabled")
        self._set_busy(True)
        self.status.set("正在扫描…")
        self._last_output_dir = None
        self.open_output_button.configure(state="disabled")
        self.manifest_info.set("")
        self.result_info.set("扫描进行中…")
        self.summary_info.set("")
        self.evaluation_info.set("")
        self.details.set("扫描完成后，选择候选记录查看验证说明和完整 SHA-256。")
        self._clear_results()
        threading.Thread(
            target=self._scan_worker,
            args=(source, output, ground_truth_records, scan_started_at, source_signature),
            daemon=True,
        ).start()

    def _scan_worker(
        self,
        source: Path,
        output: Path,
        ground_truth_records: list[GroundTruthRecord] | None,
        scan_started_at: datetime,
        source_signature: tuple[int, int],
    ) -> None:
        try:
            rows = carve_image(source, output)
            manifest = write_manifest(output.resolve(), rows)
            evaluation: EvaluationResult | None = None
            comparison_path: Path | None = None
            evaluation_summary_path: Path | None = None
            if ground_truth_records is not None:
                evaluation = evaluate_ground_truth(ground_truth_records, rows)
                comparison_path, evaluation_summary_path = write_evaluation(
                    output.resolve(), evaluation
                )
            scan_finished_at = datetime.now().astimezone()
            self._events.put(
                (
                    "success",
                    (
                        rows,
                        manifest,
                        evaluation,
                        comparison_path,
                        evaluation_summary_path,
                        source,
                        scan_started_at,
                        scan_finished_at,
                        source_signature,
                    ),
                )
            )
        except Exception as error:
            self._events.put(("error", error))

    def _poll_events(self) -> None:
        try:
            event, payload = self._events.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_events)
            return
        self._set_busy(False)
        if event == "success":
            (
                rows,
                manifest,
                evaluation,
                comparison_path,
                evaluation_summary_path,
                source,
                scan_started_at,
                scan_finished_at,
                source_signature,
            ) = payload
            self._last_report_context = (
                source,
                rows,
                evaluation,
                scan_started_at,
                scan_finished_at,
                source_signature,
            )
            self._last_output_dir = manifest.parent.resolve()
            self.open_output_button.configure(state="normal")
            self.export_report_button.configure(state="normal")
            self._ground_truth_status = (
                dict(evaluation.candidate_status) if evaluation is not None else {}
            )
            self._has_ground_truth_evaluation = evaluation is not None
            self._rows_by_filename = {str(row["filename"]): row for row in rows}
            for row in rows:
                filename = str(row["filename"])
                self.table.insert(
                    "",
                    "end",
                    iid=filename,
                    values=(
                        filename,
                        row["format"],
                        f"{int(row['offset']):,}",
                        f"{int(row['size_bytes']):,}",
                        "完整" if row["complete_boundary"] else "不完整",
                        self._format_valid(row["format_valid"]),
                    ),
                )
            complete_count = sum(row["complete_boundary"] is True for row in rows)
            valid_count = sum(row["format_valid"] is True for row in rows)
            invalid_count = sum(row["format_valid"] is False for row in rows)
            unchecked_count = len(rows) - valid_count - invalid_count
            self.result_info.set("扫描完成")
            self.summary_info.set(
                f"候选 {len(rows)}    完整边界 {complete_count}    "
                f"校验有效 {valid_count}    校验未通过 {invalid_count}    未检查 {unchecked_count}"
            )
            if evaluation is not None:
                summary = evaluation.summary
                self.evaluation_info.set(
                    f"Ground truth：精确恢复 {summary['recovered_exact_count']}/{summary['expected_present_count']}  "
                    f"候选精确率 {self._format_percent(summary['candidate_precision'])}  "
                    f"恢复率 {self._format_percent(summary['recovery_recall'])}  "
                    f"偏移匹配 {summary['offset_match_count']}/{summary['expected_offset_count']}  "
                    f"误报候选 {summary['false_positive_candidate_count']}"
                )
                self.manifest_info.set(
                    f"Manifest：{manifest.name}  ·  评估：{evaluation_summary_path.name}"
                )
            else:
                self.evaluation_info.set("")
                self.manifest_info.set(f"Manifest：{manifest}")
            self.status.set("完成")
            if rows:
                first = self.table.get_children()[0]
                self.table.selection_set(first)
                self._show_selected_details()
            else:
                self.details.set("没有检测到候选文件。空 manifest 已写入输出目录。")
        elif event == "error":
            self.status.set("扫描失败")
            self.result_info.set("未生成完整扫描结果")
            self.summary_info.set("扫描未完成；请检查路径和输出目录后重试。")
            self.evaluation_info.set("")
            self.open_output_button.configure(state="disabled")
            self.export_report_button.configure(state="disabled")
            messagebox.showerror("扫描失败", str(payload), parent=self.root)
        elif event == "report_success":
            self.status.set(f"实验报告已保存：{payload}")
        elif event == "report_error":
            self.status.set("实验报告生成失败")
            messagebox.showerror("报告生成失败", str(payload), parent=self.root)
        self.root.after(100, self._poll_events)

    def _show_selected_details(self, _event: object | None = None) -> None:
        selection = self.table.selection()
        if not selection:
            self.copy_sha_button.configure(state="disabled")
            return
        row = self._rows_by_filename.get(selection[0])
        if row is None:
            self.copy_sha_button.configure(state="disabled")
            return
        self.copy_sha_button.configure(state="normal")
        self.details.set(
            f"文件：{row['filename']}    SHA-256：{row['sha256']}\n"
            f"校验说明：{row['validation_note']}"
        )
        if self._has_ground_truth_evaluation:
            match_status = self._ground_truth_status.get(
                str(row["filename"]), "未匹配到 ground truth 源哈希（可能是误报）"
            )
            self.details.set(
                f"{self.details.get()}\nGround truth 对照：{match_status}"
            )

    @staticmethod
    def _format_percent(value: object) -> str:
        if value is None:
            return "N/A"
        return f"{float(value) * 100:.1f}%"

    def _copy_selected_sha256(self) -> None:
        selection = self.table.selection()
        if not selection:
            return
        row = self._rows_by_filename.get(selection[0])
        if row is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(str(row["sha256"]))
        self.root.update_idletasks()
        self.status.set("SHA-256 已复制")

    def _export_experiment_report(self) -> None:
        context = self._last_report_context
        if self._busy or context is None:
            return
        source = context[0]
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title="导出 PDRS 实验报告",
            initialfile=f"{source.stem}_pdrs_report.md",
            defaultextension=".md",
            filetypes=(("Markdown 文件", "*.md"), ("所有文件", "*.*")),
        )
        if not selected:
            return
        target = Path(selected).expanduser()
        if target.exists():
            messagebox.showerror(
                "文件已存在", "为避免覆盖已有报告，请选择一个新文件名。", parent=self.root
            )
            return
        self._set_busy(True)
        self.status.set("正在生成报告并计算镜像 SHA-256…")
        threading.Thread(
            target=self._report_worker,
            args=(context, target),
            daemon=True,
        ).start()

    def _report_worker(
        self,
        context: tuple[
            Path,
            list[dict[str, object]],
            EvaluationResult | None,
            datetime,
            datetime,
            tuple[int, int],
        ],
        target: Path,
    ) -> None:
        try:
            source, rows, evaluation, started_at, finished_at, source_signature = context
            report = build_experiment_report(
                source, rows, evaluation, started_at, finished_at, source_signature
            )
            saved_path = write_new_report(target, report)
            self._events.put(("report_success", saved_path))
        except Exception as error:
            self._events.put(("report_error", error))

    def _open_output_dir(self) -> None:
        if self._last_output_dir is None or not self._last_output_dir.is_dir():
            messagebox.showerror("结果目录不可用", "当前没有可打开的扫描结果目录。", parent=self.root)
            return
        try:
            os.startfile(str(self._last_output_dir))
        except OSError as error:
            messagebox.showerror("无法打开结果目录", str(error), parent=self.root)

    def _clear_results(self) -> None:
        for item in self.table.get_children():
            self.table.delete(item)
        self._rows_by_filename.clear()
        self._ground_truth_status.clear()
        self._has_ground_truth_evaluation = False
        self.copy_sha_button.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.run_button.configure(state=state)
        self.inspect_button.configure(state=state)
        self.image_button.configure(state=state)
        self.output_button.configure(state=state)
        self.image_paste_button.configure(state=state)
        self.output_paste_button.configure(state=state)
        self.ground_truth_button.configure(state=state)
        self.ground_truth_paste_button.configure(state=state)
        report_state = "disabled" if busy or self._last_report_context is None else "normal"
        self.export_report_button.configure(state=report_state)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _close(self) -> None:
        if self._busy:
            messagebox.showinfo("扫描进行中", "请等待当前只读扫描完成后再关闭窗口。", parent=self.root)
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    PDRSApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
