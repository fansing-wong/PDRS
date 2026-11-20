# Course experiment protocol

## Proposed title

**基于文件结构约束的数字文件雕刻与恢复效果评估**

The current PDRS prototype carves contiguous BMP, JPEG, PNG, and PDF candidates. This course protocol focuses primarily on PNG boundaries, with JPEG and PDF as comparison formats; BMP has a separate synthetic demo and structural tests.

## Research questions

1. How accurately can signature scanning detect known files when filesystem metadata is unavailable?
2. How do file format and content placement affect exact recovery and byte recovery rates?
3. What false positives and incomplete candidates are introduced by simple header/end-marker rules?

## Scope and hypothesis

Use only synthetic raw images generated for the experiment. The prototype reads the image in read-only mode and writes results to a separate directory. It does not interpret or recover filesystem metadata, contact physical devices, or reconstruct fragmented files.

Hypothesis: files stored contiguously with intact headers and valid format terminators will be recovered byte-for-byte more often than truncated files or files whose format markers occur in unrelated payload data. Format-aware boundary rules should reduce false positives compared with header-only extraction.

## Independent variables

- Format: BMP, JPEG, PNG, PDF; the main comparative experiment emphasizes JPEG, PNG, and PDF.
- Layout: contiguous, separated by filler bytes, truncated at end marker, truncated before end marker.
- Background: zero-filled area, random filler, and deliberately embedded decoy signatures.
- File size: small, medium, and large samples within locally available resources.

Change one factor at a time in the core comparison. Use a separate adversarial set for decoy signatures and marker-like payload data.

## Ground truth and metrics

Keep a ground-truth CSV with original filename, format, byte length, image offset, and SHA-256. Measure:

- Detection precision = true recovered candidates / all emitted candidates.
- Detection recall = source files detected / all source files inserted.
- Exact recovery rate = byte-identical files / all source files inserted.
- Byte recovery rate = matching recovered bytes / original bytes, computed for each known file.
- Runtime and peak memory for each image size.

Use SHA-256 equality to establish exact recovery. File-open success is a separate format-validity observation, not proof of byte identity.

## Procedure

1. Generate a small set of original JPEG, PNG, and PDF files with known hashes.
2. Build raw image files by placing those bytes at recorded offsets and adding controlled filler, truncation, or decoy patterns.
3. Save a ground-truth manifest before running the recovery program.
4. Scan each image with the same program version and record its CSV output, elapsed time, and peak memory.
5. Compare recovered candidate offsets and hashes against ground truth.
6. Repeat each condition at least five times for timing measurements; reuse identical images so recovery accuracy remains comparable.
7. Summarize results in tables and discuss false positives, misses, format-specific boundaries, and limitations.

## Expected results

- Contiguous, intact candidates should be detected and hash-match the originals.
- Truncated candidates should be marked incomplete or recover only a prefix.
- Decoy signatures should expose false positives and show why signatures alone cannot prove a file is valid.
- Results should show that this first milestone is a carving prototype, not general-purpose recovery: fragmentation and lost metadata require different methods.

## Report outline

1. Introduction and problem statement
2. File carving and format-boundary principles
3. Experimental design and ground-truth construction
4. Prototype architecture and read-only handling
5. Results: accuracy, byte recovery, runtime, and memory
6. Error analysis and threats to validity
7. Conclusion and next steps (additional format validation and performance measurement; filesystem metadata recovery remains outside this prototype)
