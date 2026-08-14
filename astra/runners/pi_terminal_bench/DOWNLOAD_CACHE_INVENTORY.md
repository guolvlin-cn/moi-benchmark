# Terminal-Bench 2.1 download cache inventory

This inventory covers the Pi runner's 88 tasks in the frozen Terminal-Bench
2.1 cohort after excluding `tune-mjcf` from its queue. It combines a static
scan of every included `tests/test.sh`, task Dockerfile and test helper with
completed and partial Pi verifier logs. Sizes marked **observed** came from
those logs; **estimated** entries still require a complete Linux/amd64 cache
warm-up before they can be used as a manifest.

## Cohort summary

- 82 tasks use `uv` or `uvx`: 79 request Python 3.13, two request Python
  3.11, and one requests Python 3.12.
- 81 of those scripts download the uv 0.9.5 installer. `reshard-c4-data`
  directly invokes the uv already present in its base image.
- Six tasks bypass uv and use plain pip: `build-cython-ext`,
  `fix-code-vulnerability`, `headless-terminal`, `hf-model-inference`,
  `kv-store-grpc`, and `largest-eigenval`. `mailman` remains in the uv group
  because it uses `uv pip install`.
- 81 verifier scripts run apt. Two directly clone Git repositories, with
  additional Git dependencies appearing inside Python requirements.
- No verifier script uses npm or npx, so an npm cache does not help this
  cohort.

## Priority 1: verifier-only package profiles

These dependencies are installed after the agent has finished. They can be
cached without changing agent capabilities, but must not be visible during the
agent phase. Preserve the original index and dependency resolution: changing a
default PyPI Torch install to the CPU index would change the verifier.

| Task or shared profile | Linux/amd64 cold download | Evidence | Cache action |
| --- | ---: | --- | --- |
| `torch-pipeline-parallelism`, `torch-tensor-parallelism` | about 2.93-2.96 GiB | observed; `torch==2.7.0` CUDA 12 wheels, with `transformers==4.55.0` in pipeline | One shared Python 3.13 uv profile |
| `pytorch-model-recovery` | about 2.9 GiB | estimated; default-PyPI `torch==2.7.1` resolves CUDA wheels on amd64 | Separate Python 3.13 uv profile; do not reuse historical arm64 CPU sizes |
| `mteb-retrieve` | about 2.85-2.95 GiB | observed; `mteb==1.36.8` pulls a CUDA 13 Torch stack | Separate Python 3.13 uv profile |
| `sam-cell-seg` | about 285 MiB packages | observed; CPU-index Torch 2.5.1, torchvision 0.20.1, OpenCV and scientific stack | Python 3.11 CPU-index profile |
| `pytorch-model-cli` | about 261 MiB packages | observed; CPU-index Torch 2.7.1, torchvision 0.22.1 and OpenCV | Python 3.13 CPU-index profile |
| `install-windows-3.11` | about 116 MiB including bootstrap | observed; OpenCV and NumPy dominate | Scientific/OpenCV Python 3.13 profile |
| `build-pov-ray` | about 103 MiB including bootstrap | observed; SciPy, NumPy and scikit-image dominate | Scientific Python 3.13 profile |
| `bn-fit-modify` | about 94 MiB including bootstrap | observed; SciPy, pandas and NumPy dominate | Scientific Python 3.13 profile |
| `modernize-scientific-stack` | about 84 MiB | observed; SciPy, NumPy, pandas and matplotlib | Scientific Python 3.13 profile |
| `adaptive-rejection-sampler` | about 83 MiB including bootstrap | observed | Scientific Python 3.13 profile |
| `video-processing` | about 83 MiB | observed; OpenCV contrib is about 66 MiB | OpenCV Python 3.13 profile |
| `reshard-c4-data` | about 81 MiB packages | observed; PyArrow is about 48 MiB | PyArrow Python 3.13 profile |
| `multi-source-data-merger` | about 74 MiB | observed; PyArrow, pandas and NumPy | PyArrow Python 3.13 profile |
| `financial-document-processor` | about 61 MiB including bootstrap | observed | Scientific Python 3.13 profile |
| `path-tracing`, `path-tracing-reverse` | about 54 MiB including bootstrap | observed | Small scientific Python 3.13 profile |

The Torch 2.7.0 profile is dominated by an 825 MiB Torch wheel, 545 MiB
cuDNN, 375 MiB cuBLAS, 207 MiB cuSPARSE, 192 MiB NCCL, 191 MiB cuFFT,
151 MiB cuSOLVER, 150 MiB cuSPARSELt, and 149 MiB Triton. This explains why
lowering uv concurrency alone cannot make a cold 2.9 GiB install fit the
30-minute verifier timeout.

The three large CUDA profiles are not interchangeable: Torch 2.7.0 and 2.7.1
have different wheel sets, and the MTEB resolution uses CUDA 13 rather than
CUDA 12. The three logical profile downloads sum to roughly 8.7 GiB before the
CPU and scientific profiles. A content-addressed host cache may reduce the
physical total to roughly 7.4-7.8 GiB if Torch 2.7.0 and 2.7.1 resolve the
same CUDA 12 dependency wheels; only a complete warm-up can confirm that
reuse. Do not copy a global cache into every trial: each task has a 10GB
storage limit, and uv also needs space for extracted packages and its tool
environment.

## Priority 2: verifier-only direct assets

| Task | Asset | Size | Cache action |
| --- | --- | ---: | --- |
| `reshard-c4-data` | C4 `en/c4-train.00009-of-01024.json.gz` | 318,185,592 bytes observed | Copy into the verifier only after the agent phase |
| `sam-cell-seg` | `mobile_sam.pt` | 40,728,226 bytes observed | Cache with the matching MobileSAM source snapshot |
| `fix-ocaml-gc` | `sadiqj/ocaml` source | about 6.5 MiB | Local Git mirror |
| `train-fasttext` | `facebookresearch/fastText` source | about 4 MiB | Local Git mirror |
| `build-cython-ext` | pyknotid 0.5.3 source | about 1.8 MiB | Local Git mirror |
| `filter-js-from-html` | GitHub `master.zip` | 136,398 bytes observed | Low priority; record the resolved revision because the URL is mutable |

Only the C4 shard and MobileSAM weight materially affect the 48-hour budget.
Public verifier assets may be cached, but tests, expected outputs, solutions,
and task answers must never be placed in the cache.

## Priority 3: downloads available to the agent

These resources are part of solving the task. A verifier-only copy would
change task difficulty. Cache them only through the same transparent URL,
Git, or Hugging Face proxy for Pi, Astra, and Hermes.

| Task | Resource | Size or observed risk |
| --- | --- | --- |
| `mteb-leaderboard` | `embeddings-benchmark/results` history | about 574 MiB as a Git repository; an alternative four-parquet path is about 290 MiB |
| `hf-model-inference` | DistilBERT SST-2 model | `model.safetensors` is 267,832,560 bytes |
| `caffe-cifar-10` | CIFAR-10 binary archive | about 170.5 MB; a 170,052,171-byte partial archive failed gzip validation, while the expected complete transfer was about 170,498,071 bytes, so require gzip/tar integrity rather than trusting size |
| `mteb-retrieve` | BGE embedding model | about 91 MB observed |
| `install-windows-3.11` | QEMU 5.2 source, for solutions that rebuild it | 106,902,800 bytes |
| `count-dataset-tokens` | Qwen tokenizer and OpenThoughts metadata | tens of MiB; cache only the tokenizer and selected data files, not the full model |

Stan, CRAN, opam, and other solver-selected dependency trees are better served
by transparent package proxies than by task-specific hidden files.

## Already carried by Docker image layers

The runner uses prebuilt task images and `--no-force-build`. These large files
normally need Docker's image cache, not a second runtime cache:

- the two QEMU tasks' Alpine extended ISO, about 957 MiB each;
- the GPT-2 checkpoint, 497,759,232 bytes;
- Yelp train and test parquet files, 299,436,850 and 23,515,519 bytes;
- the Windows 3.11 disk image, 268,435,456 bytes;
- the C4 `00000` shard in the reshard base image, about 319 MB;
- GCC 13.2 source, about 125 MB compressed; and
- `oewn.sqlite`, 50,606,080 bytes.

Keep these Docker images locally. Download the source assets separately only
when rebuilding the images.

## Cache layout and rollout order

Use Linux/amd64 and uv 0.9.5 to warm package profiles; a macOS or arm64 uv
cache is not reusable by these task containers. Store each profile separately
by Python minor, index, and top-level requirements. Record resolved wheel file
names and versions before declaring a profile complete; estimates in this file
are not a lock manifest.

Recommended order:

1. Warm the shared Torch 2.7.0 CUDA 12 profile.
2. Warm the Torch 2.7.1 CUDA 12 and MTEB/CUDA 13 profiles separately.
3. Cache the C4 `00009` shard and MobileSAM assets for verifier-only injection.
4. Warm CPU Torch/OpenCV and common scientific/PyArrow profiles.
5. Put CIFAR-10, DistilBERT, and MTEB results behind a transparent cache shared
   by all three C0 products.
6. Use apt, PyPI, CRAN, and opam proxies for the long tail.

The current verifier copies its bootstrap cache only after the agent finishes.
Large package profiles should follow the same visibility rule, but should be
selected per task rather than copying the entire cache. A static bind mount is
not equivalent because it is visible to the agent from container startup.
