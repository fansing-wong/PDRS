# PDRS — 数据恢复技术课程实验工具

PDRS（Personal Data Recovery Study）是一个面向可重复实验的只读恢复原型。它扫描用户明确选择的普通 raw 镜像文件，支持 BMP、JPEG、PNG、PDF、SQLite 连续雕刻，并提供实验性的 FAT32 误删文件提取。

> **范围说明：** 程序只处理常规镜像文件，不访问物理磁盘或系统实时设备。FAT32 误删恢复扫描根目录及仍可访问的活动子目录中的删除短文件名项，并尝试从相邻 LFN 槽恢复显示名称；默认跳过可见碎片链，显式启用实验选项后才尝试重组完整 FAT 链。另一个独立选项可扫描 FAT 链完整、且不与活动数据重叠的已删除目录中的直接文件项；不会递归进入更深的已删除目录。删除短名首字符已丢失，因此 LFN 校验和无法完整核验。若删除后文件 FAT 链已清空，仍只能按连续存储假设提取。它不是生产级数据恢复软件；请仅处理自己制作或获准检查的镜像副本。

## 功能

- 只读 `mmap` 扫描普通镜像；候选文件和报告写入独立目录。
- 连续文件雕刻：BMP、JPEG、PNG、PDF、SQLite 主数据库。SQLite 候选不超过 64 MiB 时运行 `PRAGMA quick_check`；更大的候选会跳过完整检查并标记。
- **实验性 FAT32 误删恢复**：读取卷的第一张 FAT，扫描根目录和活动子目录的簇链，提取删除项并尝试重建 LFN 显示名；输出名经过安全处理且带偏移标识。默认跳过可见碎片链；显式启用重组后，仅在完整链和活动文件分配映射均可确认且无簇冲突时按逻辑顺序读取。另可选择进入链完整且无活动数据冲突的已删除目录，扫描其直接文件项。FAT 链已清空时仍按连续簇假设，不做格式验证，并报告扫描目录数和字节数。
- 镜像结构只读检查 MBR/GPT、FAT32/exFAT 引导参数、ext 超级块和 NTFS 引导标记。
- Tkinter 图形界面、Ground Truth 对照、SHA-256、CSV manifest 和 Markdown 扫描报告。

误删恢复要求目录项及数据仍可读、数据尚未覆盖，并且候选字节符合连续布局假设，或有完整可读的 FAT 链可跟随。格式校验通过也不能证明文件来源或真实性。

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

完整 FAT 链碎片重组为可选实验模式：

```powershell
.\.venv\Scripts\pdrs.exe recover-fat32-deleted .\fat32.img .\fat32_reassembled --ground-truth .\ground_truth.csv --reassemble-fragmented
```

此模式会拒绝与活动目录、活动文件或其他恢复候选共用簇的数据。manifest 的 `source_extents` 列列出镜像物理片段（`offset:length`，分号分隔）；碎片文件的 `offset` 是首段起点，`end_offset_exclusive` 留空。

扫描完整链的已删除目录中的直接文件项（可与上面的碎片重组选项组合）：

```powershell
.\.venv\Scripts\pdrs.exe recover-fat32-deleted .\fat32.img .\fat32_deleted_dirs --ground-truth .\ground_truth.csv --scan-deleted-directories
```

程序只扫描目录项仍可读、FAT 链完整且不与活动目录或活动文件共用簇的已删除目录；结果 manifest 标记 `parent_deleted_directory` 和 `parent_directory_cluster`。扫描最多 256 个已删除目录、累计 64 MiB，不递归扫描更深的已删除子目录。目录 FAT 链已清除或不完整时会跳过。

输出目录不存在时会创建；已存在时必须为空。程序不会覆盖已有结果。输入镜像以只读方式打开。

启动图形界面：

```powershell
.\.venv\Scripts\python.exe .\run_gui.py
```

## 合成实验

FAT32 v0.16 历史矩阵（512 B、1 KiB、2 KiB 簇）：

```powershell
.\.venv\Scripts\python.exe .\examples\make_fat32_deleted_demo.py --output-dir .\examples\fat32_deleted_demo_v16 --sectors-per-cluster 1
.\.venv\Scripts\python.exe .\examples\run_fat32_deleted_demo.py --demo-dir .\examples\fat32_deleted_demo_v16
.\.venv\Scripts\python.exe .\examples\run_fat32_layout_matrix_v16.py
```

单次演示分别报告 SHA-256/偏移精确匹配和 LFN 名称匹配；矩阵结果汇总到 `matrix_summary.csv`，逐样本数据布局计数写入 `data_layout_summary.csv`。

v0.17 可选碎片重组矩阵新增一个完整碎片链正向样本，以及活动文件、已删除目录和中断链负向样本：

```powershell
.\.venv\Scripts\python.exe .\examples\make_fat32_fragmented_demo_v17.py --output-dir .\examples\fat32_deleted_demo_v17 --sectors-per-cluster 1
.\.venv\Scripts\python.exe .\examples\run_fat32_fragmented_demo_v17.py --demo-dir .\examples\fat32_deleted_demo_v17
.\.venv\Scripts\python.exe .\examples\run_fat32_layout_matrix_v17.py
```

v0.18 已删除目录直接文件扫描矩阵会自动生成三种簇大小的独立合成镜像，并只修补合成镜像中已知目录的 FAT 结束链：

```powershell
.\.venv\Scripts\python.exe .\examples\run_deleted_directory_matrix_v18.py
```

矩阵输出在 `examples/fat32_deleted_directory_matrix_v18`。数据集包含四个原有恢复目标、一个已删除目录内文件目标，以及活动文件和中断链两个预期缺失控制。验证结果在三种簇大小下均为 5/5 精确恢复、0 个误报；这些数字只描述合成样本。

v0.19 增加多簇目录、跨簇 LFN 和簇复用负向场景：

```powershell
.\.venv\Scripts\python.exe .\examples\run_deleted_directory_matrix_v19.py
```

多簇/LFN 场景在三种簇大小下均为 6/6 精确恢复；复用控制均拒绝与活动文件共用尾簇的已删除目录，其他 4/4 目标精确恢复。两个场景都没有误报。结果写入 `examples/fat32_deleted_directory_matrix_v19`；这仍是固定合成样本，不代表真实磁盘的恢复率。

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

- FAT32 删除项恢复扫描根目录和活动子目录中的短文件名项；可从相邻删除 LFN 槽重建显示名，但因短名首字符丢失无法完整核验校验和。目录树扫描不完整时会停止提取，并跳过与活动目录簇重叠的数据范围。可选的已删除目录扫描仅覆盖完整、不与活动数据重叠目录链中的直接文件项，不递归；目录链已清除或分配无法安全确认时会跳过。
- 默认跳过可见碎片链；显式启用实验模式后，只有完整 FAT 链、完整活动文件分配映射且无已知簇冲突的候选才会重组。链中断、冲突或活动文件映射不完整时仍跳过；FAT 链清空时仍按连续区域假设，可能无法恢复或产生错误候选。
- 不恢复 NTFS/exFAT/ext/APFS/HFS+/F2FS 的文件系统删除记录，不扫描物理设备。
- SQLite 只雕刻主数据库，不重放 WAL、不恢复删除行、不解析应用 schema。
- 部分介质损坏只在合成镜像中用零填充和截断模拟；不读取坏道、不修复文件。
- APFS、HFS+、F2FS 和完整 NTFS 解析尚未实现；FAT32 碎片重组仍属受限实验功能。

## License

本项目尚未决定许可证；公开前需要由项目所有者确定代码和文档的授权条款。

---

## English

PDRS is a read-only educational prototype for regular raw image files. It carves contiguous BMP, JPEG, PNG, PDF, and SQLite main-database candidates. An experimental command scans FAT32 root directories and active subdirectories for deleted short-name entries and attempts to reconstruct adjacent deleted LFN slots. Visible fragmented chains are skipped by default; an explicit experimental option reassembles complete chains after active-allocation overlap checks. When deletion has cleared FAT links, it still assumes file data is contiguous. The lost short-name first byte prevents full LFN checksum verification. It does not scan physical devices or enter deleted directories.

Filesystem support is independent of the host OS. NTFS currently has marker recognition only; ext support is superblock metadata only; APFS, HFS+, and F2FS are not parsed. SQLite is treated as a generic main database: no WAL replay, deleted-row recovery, or app-schema extraction. Use authorized image copies only. See [the recovery roadmap](docs/RECOVERY_ROADMAP.md). The license has not been selected yet.
