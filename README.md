# PDRS — 数据恢复技术课程实验工具

PDRS（Personal Data Recovery Study）是一个面向可重复实验的只读恢复原型。它扫描用户明确选择的普通 raw 镜像文件，支持 BMP、JPEG、PNG、PDF、SQLite 连续雕刻，并提供实验性的 FAT32 误删文件提取。

> **范围说明：** 程序只处理常规镜像文件，不访问物理磁盘或系统实时设备。FAT32 误删恢复仅扫描根目录及仍可访问的活动子目录中的 8.3 短文件名项，并假设文件数据连续存储；不进入已删除目录、不恢复长文件名、不重组碎片。它不是生产级数据恢复软件；请仅处理自己制作或获准检查的镜像副本。

## 功能

- 只读 `mmap` 扫描普通镜像；候选文件和报告写入独立目录。
- 连续文件雕刻：BMP、JPEG、PNG、PDF、SQLite 主数据库。SQLite 候选不超过 64 MiB 时运行 `PRAGMA quick_check`；更大的候选会跳过完整检查并标记。
- **实验性 FAT32 误删恢复**：读取卷的第一张 FAT，扫描根目录和活动子目录的簇链，提取删除的短文件名项；文件内容按连续簇假设，不做格式验证，并报告扫描目录数和字节数。
- 镜像结构只读检查 MBR/GPT、FAT32/exFAT 引导参数、ext 超级块和 NTFS 引导标记。
- Tkinter 图形界面、Ground Truth 对照、SHA-256、CSV manifest 和 Markdown 扫描报告。

误删恢复只能在目录项和数据仍可读、数据尚未覆盖且连续性假设成立时工作。格式校验通过也不能证明文件来源或真实性。

## 平台和文件系统

能力由文件系统结构决定，不由运行程序的操作系统名称决定。当前有有限 FAT32 删除项恢复实验和 FAT32/exFAT、ext 超级块等元数据检查；NTFS 仅识别引导标记，尚未实现 NTFS 删除文件恢复。Android F2FS 与 Apple APFS/HFS+ 尚未解析。SQLite 文件按通用数据库雕刻，不解释应用私有 schema、不重放 `-wal`，也不恢复删除行。设备加密、应用沙盒和闪存 TRIM 可能使数据无法恢复。详见 [恢复场景与平台路线图](docs/RECOVERY_ROADMAP.md)。

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

常规镜像扫描和结构查看：

```powershell
.\.venv\Scripts\pdrs.exe carve .\sample.img .\recovered
.\.venv\Scripts\pdrs.exe inspect .\sample.img
```

实验性 FAT32 删除项恢复：

```powershell
.\.venv\Scripts\pdrs.exe recover-fat32-deleted .\fat32.img .\fat32_recovered --ground-truth .\ground_truth.csv
```

输出目录不存在时会创建；已存在时必须为空。程序不会覆盖已有结果。输入镜像以只读方式打开。

启动图形界面：

```powershell
.\.venv\Scripts\python.exe .\run_gui.py
```

## 合成实验

FAT32 根目录、活动子目录和已删除目录负向对照演示及 Ground Truth：

```powershell
.\.venv\Scripts\python.exe .\examples\make_fat32_deleted_demo.py --output-dir .\examples\fat32_deleted_demo_v11
.\.venv\Scripts\python.exe .\examples\run_fat32_deleted_demo.py --demo-dir .\examples\fat32_deleted_demo_v11
```

SQLite 误删残留、零填充和截断场景：

```powershell
.\.venv\Scripts\python.exe .\examples\make_recovery_scenario_set_v1.py
.\.venv\Scripts\python.exe .\examples\run_recovery_scenario_set_v1.py
```

ext4 结构演示：

```powershell
.\.venv\Scripts\python.exe .\examples\make_ext4_structure_demo.py
.\.venv\Scripts\pdrs.exe inspect .\examples\ext4_structure_demo\ext4_demo.img
```

生成脚本会拒绝覆盖已有数据；生成的镜像和结果不加入 Git。实验方法见 [EXPERIMENT.md](EXPERIMENT.md)，路线图见 [docs/RECOVERY_ROADMAP.md](docs/RECOVERY_ROADMAP.md)。

## 开发检查

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

GitHub Actions 在 Windows 与 Ubuntu 上使用 Python 3.12、3.13 执行单元测试。

## 局限性

- FAT32 删除项恢复扫描根目录和活动子目录中的短文件名项；目录树扫描不完整时会停止提取，并跳过与活动目录簇重叠的数据范围。不进入已删除目录，不解析 LFN，无法恢复原文件名首字符。
- FAT32 恢复根据目录项中的首簇号和文件大小读取连续区域；碎片文件可能被错误拼接或无法恢复。
- 不恢复 NTFS/exFAT/ext/APFS/HFS+/F2FS 的文件系统删除记录，不扫描物理设备。
- SQLite 只雕刻主数据库，不重放 WAL、不恢复删除行、不解析应用 schema。
- 部分介质损坏只在合成镜像中用零填充和截断模拟；不读取坏道、不修复文件。
- APFS、HFS+、F2FS、完整 NTFS 解析和通用碎片重组尚未实现。

## License

本项目尚未决定许可证；公开前需要由项目所有者确定代码和文档的授权条款。

---

## English

PDRS is a read-only educational prototype for regular raw image files. It carves contiguous BMP, JPEG, PNG, PDF, and SQLite main-database candidates. An experimental command scans FAT32 root directories and active subdirectories for deleted short-name entries, assuming file data is contiguous. It does not scan physical devices, enter deleted directories, restore long filenames, or reassemble fragmented files.

Filesystem support is independent of the host OS. NTFS currently has marker recognition only; ext support is superblock metadata only; APFS, HFS+, and F2FS are not parsed. SQLite is treated as a generic main database: no WAL replay, deleted-row recovery, or app-schema extraction. Use authorized image copies only. See [the recovery roadmap](docs/RECOVERY_ROADMAP.md). The license has not been selected yet.
