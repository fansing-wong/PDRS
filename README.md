# PDRS — 数据恢复技术课程实验工具

PDRS（Personal Data Recovery Study）是一个用于可重复实验的只读文件雕刻原型。它扫描用户明确选择的普通 raw 镜像文件，提取连续的 BMP、JPEG、PNG、PDF 和 SQLite 主数据库候选，并记录偏移、边界、SHA-256 和 CSV manifest。

> **范围说明：** PDRS 不直接访问物理磁盘，不读取操作系统的实时磁盘设备，不恢复文件系统目录/删除记录，不提取 SQLite 已删除行，也不重组碎片文件。镜像结构查看器只读有限分区、卷引导和 ext 超级块元数据。它不是生产级数据恢复软件；请仅处理自己制作或获准检查的镜像副本。

## 功能

- 只读 `mmap` 扫描普通镜像文件；候选数据和报告写入单独目录。
- 连续文件雕刻：BMP、JPEG、PNG、PDF、SQLite 数据库。
- SQLite 检查文件头、页数边界、第一页 B-tree，并对不超过 64 MiB 的候选运行 `PRAGMA quick_check`；更大的候选会跳过完整检查并明确标记。
- BMP 检查受支持的 DIB 头、尺寸、调色板偏移及像素数组边界；不解码像素。
- PNG 检查块边界、CRC、IDAT zlib 流、扫描线长度和受支持的隔行布局。
- 安装可选验证依赖后，用 Pillow 解码 JPEG、用 pypdf 严格解析 PDF。
- `pdrs inspect` 只读查看 MBR/GPT、FAT32/exFAT 引导参数、ext 超级块，以及 NTFS 引导标记。
- Tkinter 图形界面、Ground Truth 对照、SHA-256、manifest 和 Markdown 扫描报告。
- 合成实验模拟“文件目录信息丢失但文件字节还在”、512 字节零填充和镜像截断；这些不会访问真实磁盘。

这些检查不是修复功能，也不代表候选数据一定完整、可信或来自特定应用。Ground Truth 哈希对照适用于已知原文件的合成实验。

## 平台和文件系统

支持能力由文件系统格式决定，不由运行 PDRS 的操作系统名称决定。当前只实现有限的 FAT32/exFAT、ext 超级块和 NTFS 引导标记检查；未实现完整 NTFS、F2FS、APFS 或 HFS+ 解析。Android 或桌面应用的 SQLite 文件只按通用 SQLite 数据库雕刻，不解释应用私有 schema，也不合并 `-wal` 日志。设备加密、应用沙盒和闪存 TRIM 可能令数据不可恢复。详见 [恢复场景与平台路线图](docs/RECOVERY_ROADMAP.md)。

## 环境要求

- Python 3.12 或更高版本。
- Tkinter 用于桌面界面（Windows 官方 Python 安装通常已包含）。

## 安装与运行（Windows PowerShell）

在项目根目录逐行执行：

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[validation]"
.\.venv\Scripts\pdrs.exe --help
```

扫描镜像并查看有限的分区/卷结构：

```powershell
.\.venv\Scripts\pdrs.exe carve .\sample.img .\recovered
.\.venv\Scripts\pdrs.exe inspect .\sample.img
.\.venv\Scripts\pdrs.exe inspect --json .\sample.img
```

也可以启动桌面界面：

```powershell
.\.venv\Scripts\python.exe .\run_gui.py
```

输出目录不存在时会创建；已存在时必须为空。程序不会覆盖已有结果。输入镜像以只读方式打开。

## 合成实验

误删残留数据和介质损坏模拟：

```powershell
.\.venv\Scripts\python.exe .\examples\make_recovery_scenario_set_v1.py
.\.venv\Scripts\python.exe .\examples\run_recovery_scenario_set_v1.py
```

生成 ext4 分区结构演示镜像并只读检查：

```powershell
.\.venv\Scripts\python.exe .\examples\make_ext4_structure_demo.py
.\.venv\Scripts\pdrs.exe inspect .\examples\ext4_structure_demo\ext4_demo.img
```

该合成镜像只包含用于识别的分区和超级块字段，不是可挂载文件系统。

PNG 兼容性实验：

```powershell
.\.venv\Scripts\python.exe .\examples\make_png_compatibility_set_v4.py
.\.venv\Scripts\python.exe .\examples\run_png_compatibility_v4.py
```

生成的数据集和运行结果不纳入 Git；脚本会拒绝覆盖已有输出。实验流程见 [EXPERIMENT.md](EXPERIMENT.md)，平台发展计划见 [docs/RECOVERY_ROADMAP.md](docs/RECOVERY_ROADMAP.md)，课程报告草稿见 [PDRS_REPORT_DRAFT.md](PDRS_REPORT_DRAFT.md)。

## 开发检查

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[validation]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

GitHub Actions 会在 Windows 与 Ubuntu 上使用 Python 3.12、3.13 执行单元测试。

## 目录

- `src/pdrs/`：CLI、GUI、雕刻、镜像结构、评估和报告代码。
- `tests/`：主程序单元测试。
- `examples/`：合成数据生成器和实验脚本；大型生成数据不随仓库分发。
- `docs/RECOVERY_ROADMAP.md`：误删/损坏场景和跨平台文件系统路线图。
- `EXPERIMENT.md`：实验流程说明。
- `PDRS_REPORT_DRAFT.md`：此前课程实验结果草稿。

## 局限性

- 雕刻只适用于连续数据；碎片文件可能漏检、被截断，或把间隙误收进候选。
- SQLite 只雕刻完整主数据库字节；不重放 WAL、不恢复删除行、不解析应用 schema。
- ext 只读取超级块元数据；NTFS 只识别引导扇区标记；FAT32/exFAT 也不读取目录和文件内容。
- 误删数据实验模拟“数据残留、目录信息缺失”的输入布局，并没有恢复真正文件系统删除记录。
- 部分损坏实验用零填充/截断模拟，不读取真实坏道、不控制硬盘，也不修复损坏文件。
- APFS、HFS+、F2FS、完整 NTFS、文件系统目录/簇链恢复和碎片重组尚未实现。

## License

本项目尚未决定许可证；公开前需要由项目所有者确定代码和文档的授权条款。

---

## English

PDRS is a read-only educational prototype that carves contiguous BMP, JPEG, PNG, PDF, and SQLite main-database candidates from user-selected regular raw image files. It records offsets, boundaries, SHA-256 hashes, and manifests for repeatable experiments.

It does not access physical disks, recover filesystem directories or deleted records, recover deleted SQLite rows, replay SQLite WAL files, or reassemble fragmented files. The structure viewer reads only limited MBR/GPT, FAT32/exFAT, NTFS-marker, and ext-superblock metadata. The synthetic deletion and damage conditions use retained bytes, zero-filled regions, or truncation; they are not tests on failing hardware.

Support depends on filesystem structures, not the host operating system. Current support does not include full NTFS, F2FS, APFS, or HFS+ parsing. Android or desktop application databases are treated as generic SQLite files, without application schema extraction or WAL merging. Encryption, app sandboxes, and flash discard/TRIM may prevent recovery. See [the recovery roadmap](docs/RECOVERY_ROADMAP.md).

Requires Python 3.12+. Install with `python -m pip install -e ".[validation]"`; run `pdrs carve IMAGE OUTPUT`, `pdrs inspect IMAGE`, or launch the Tkinter GUI with `python run_gui.py`. The output directory must be empty if it already exists. A license has not been selected yet.
