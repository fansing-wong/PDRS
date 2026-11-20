# Five-run summary

## Results

Each scenario used the same synthetic image for five end-to-end CLI runs. Candidate and hash outcomes were identical across all five runs.

| Scenario | Mean runtime (s) | Median (s) | Range (s) | Candidates / run | True header candidates / run | False positives / run | Exact SHA-256 matches / run |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 0.473261 | 0.478392 | 0.440470–0.520212 | 1 | 1 | 0 | 1 |
| Truncated | 0.504167 | 0.497277 | 0.458877–0.554376 | 1 | 1 | 0 | 0 |
| Decoy signature | 0.444906 | 0.433421 | 0.428804–0.496206 | 1 | 0 | 1 | 0 |
| Fragmented | 0.435796 | 0.420989 | 0.415850–0.466115 | 1 | 1 | 0 | 0 |

## Accuracy summary

Across the four conditions, the scanner emitted four candidates per trial: three began at genuine ground-truth file offsets and one was the decoy. For this small demonstration, candidate precision was 3/4 (**75%**), header detection recall was 3/3 (**100%**), and exact recovery among genuine inputs was 1/3 (**33.3%**).

The repeated runs do not increase the number of independent test files. They provide five timing observations per fixed image. Accuracy stayed constant because each run scanned identical bytes.

## Interpretation

- The baseline was recovered byte-for-byte in all runs.
- The truncated image produced a candidate in all runs, but none matched the complete original hash; the boundary flag was false.
- The decoy produced a false positive in all runs, and the boundary flag was true. A marker match is therefore not format validation.
- The fragmented image produced a candidate in all runs, but none matched the original hash. A boundary flag of true did not imply successful reassembly.
- Mean runtimes are around 0.44–0.50 seconds for images under 1 KB. They include Python process startup and manifest writing, so they mostly describe this demonstration environment and are not a useful measure of scan throughput or scaling.

## Limitations

Each condition currently has one unique synthetic image. Expand the dataset with several independent files per format and larger image sizes before drawing general conclusions. The five-run timing script does not measure peak memory. Preserve `benchmark_summary.csv` as the run-level source data.
