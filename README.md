# PDRS — 数据恢复技术课程实验工具

PDRS（Personal Data Recovery Study）是一个面向课程实验的只读文件雕刻原型。它只扫描用户明确选择的普通 raw 镜像文件，提取连续的 BMP、JPEG、PNG、PDF 候选，并记录偏移、边界、SHA-256 和 CSV manifest，便于定量评估。

> **范围说明：** PDRS 不访问物理磁盘，不解析文件系统目录项或删除记录，也不跟随簇链或重组碎片文件。镜像结构查看器只报告有限的分区和卷引导信息。它不是生产级数据恢复软件；请仅处理自己制作或获准检查的镜像副本。

## 功能

- 只读 `mmap` 扫描普通镜像文件；候选数据写入单独的空目录。
- 连续文件雕刻：BMP、JPEG、PNG、PDF。
- BMP 检查受支持的 DIB 头、尺寸、调色板偏移及像素数组边界；不解码像素。
- PNG 检查块边界、CRC、IDAT zlib 流、扫描线长度和受支持的隔行布局。
- 安装可选验证依赖后，用 Pillow 解码 JPEG、用 pypdf 严格解析 PDF。
- `pdrs inspect` 只读查看 MBR/GPT 分区表、FAT32/exFAT 引导参数及 exFAT 主/备引导区校验和；NTFS 仅识别引导扇区标记。
- Tkinter 图形界面、Ground Truth 对照、SHA-256、manifest 和 Markdown 扫描报告。

这些格式检查不是修复功能，也不代表候选文件一定完整或可信。Ground Truth 的哈希对照适用于已知原文件的合成实验。

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

扫描一个镜像并查看分区/卷结构：

```powershell
.\.venv\Scripts\pdrs.exe carve .\sample.img .\recovered
.\.venv\Scripts\pdrs.exe inspect .\sample.img
.\.venv\Scripts\pdrs.exe inspect --json .\sample.img
```

也可以启动桌面界面：

```powershell
.\.venv\Scripts\python.exe .\run_gui.py
```

输出目录不存在时会创建；已存在时必须为空。程序不会覆盖已有结果。输入镜像以只读方式打开，扫描候选和报告写到输出目录。

若不需要 JPEG/PDF 可选解析器，安装基础包即可：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

## 合成实验

生成 BMP 演示镜像及 Ground Truth，然后扫描：

```powershell
.\.venv\Scripts\python.exe .\examples\make_bmp_demo.py
.\.venv\Scripts\pdrs.exe carve .\examples\bmp_demo_set\bmp_demo.img .\examples\bmp_demo_set\recovered
```

可复现的 PNG 兼容性实验：

```powershell
.\.venv\Scripts\python.exe .\examples\make_png_compatibility_set_v4.py
.\.venv\Scripts\python.exe .\examples\run_png_compatibility_v4.py
```

生成的数据集和运行结果不纳入 Git；生成脚本会在对应输出目录已存在时拒绝覆盖。更多实验方法见 [EXPERIMENT.md](EXPERIMENT.md)，课程报告草稿见 [PDRS_REPORT_DRAFT.md](PDRS_REPORT_DRAFT.md)。

## 开发检查

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[validation]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

GitHub Actions 会在 Windows 与 Ubuntu 上使用 Python 3.12、3.13 执行相同的单元测试。

## 目录

- `src/pdrs/`：CLI、GUI、扫描、镜像结构、评估和报告代码。
- `tests/`：主程序单元测试。
- `examples/`：合成数据生成器和实验脚本；大型数据集由脚本生成，不随仓库分发。
- `EXPERIMENT.md`：实验流程说明。
- `PDRS_REPORT_DRAFT.md`：课程报告草稿。

## 局限性

- 雕刻只适用于连续数据；碎片文件可能漏检、被截断，或把间隙误收进候选。
- JPEG 结束位置基于标记；PDF 结束标记可能出现在嵌入对象中间。可选解析器也不能证明文件来源或真实性。
- BMP 校验只覆盖声明边界及受支持头部，不解码图像内容。
- 文件系统查看器不枚举目录、不恢复删除记录、不读取簇链内容，也不访问物理设备。
- PNG/JPEG/PDF/BMP 的格式验证范围有限；程序不修复损坏文件，也不提供取证完整性认证。
- 碎片重组、目录恢复、ZIP 类格式和文件修复不属于主程序功能。

## License

本项目尚未决定许可证；公开前需要由项目所有者确定代码和文档的授权条款。

---

## English

PDRS is a read-only educational prototype for carving contiguous BMP, JPEG, PNG, and PDF candidates from user-selected raw image files. It records offsets, boundaries, SHA-256 hashes, and manifests for reproducible experiments.

It does not access physical disks, recover filesystem directories or deleted records, follow cluster chains, or reassemble fragmented files. The structure viewer reports only limited partition and boot-sector metadata. It is not production recovery software. Use authorized image copies only.

Requires Python 3.12+. Install with `python -m pip install -e ".[validation]"`; run `pdrs carve IMAGE OUTPUT`, `pdrs inspect IMAGE`, or launch the Tkinter GUI with `python run_gui.py`. The output directory must be empty if it already exists. See the Chinese sections above for examples and limitations.

A license has not been selected yet; reuse terms must be decided before public release.