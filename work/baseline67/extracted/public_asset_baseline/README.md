# 具身仿真资产生成 Baseline（分数67+）

提供两条互不混淆的复现路径：

1. **快速精确复现**：使用仓库内两份冻结中间包，在无 GPU 环境下生成可提交 ZIP，并做 ZIP、OpenUSD 与轻量物理校验。
2. **从官方输入重建**：仅以 `question.zip` 与 `submission_example.zip` 为竞赛数据输入，在阿里云 GPU 上从视频生成 USD 资产、纹理、碰撞与过程收据。

两条路径有不同目标。快速路径重建的是已验证候选的同一字节；从官方输入重建路径是可审计的生成研究基线，输出合法候选但不承诺与快速路径完全一致，可能由于模型、驱动和数值精度导致差异。

## 解题策略

赛题目标是把视频中的物体转换为可提交、可物理仿真的 USD 资产。生成路径按以下顺序工作：

```text
官方 ZIP
  -> 输入哈希、CRC 与 34 题/视频清单
  -> 抽帧与多样性/清晰度选视角
  -> 前景分割
  -> Shape + Paint 重建
  -> 视觉网格、纹理、碰撞体、刚体 USD
  -> OpenUSD 与 120 步 MuJoCo 校验
  -> submission.zip
```

它把竞赛原始数据保持在仓库外；每次运行写出输入哈希、视角选择、网格/资产清单、运行环境、命令记录和验证报告。快速路径则把已存在的两个中间 ZIP 作为明确输入：保留基础中间包的全部成员，仅以供体中两个经过哈希锁定的 USD 成员替换同名成员，再使用固定 ZIP 元数据写出最终包。

## 路径 A：无需 GPU 的快速精确复现

仓库已包含以下非原始数据的中间产物：

```text
artifacts/intermediate/base_submission.zip
artifacts/intermediate/donor_submission.zip
artifacts/reference/submission.zip
evidence/online_score_evidence.json
```

其中 `evidence/online_score_evidence.json` 是外部线上评测结果的事实记录，不是、也不可能是代码生成的实验过程。它记录的候选 SHA-256 与 `artifacts/reference/submission.zip` 相同，结果为 `67.6000`。其余过程文件都由本仓库脚本生成并可本地复核。

安装 Python 3.10+ 后执行：

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
python -m pip install -r requirements-dev.txt

python scripts/quick_reproduce.py --output-root quick_output
```

这里有意使用普通安装而不是可编辑安装，因此仓库即使位于包含中文字符的目录中也可正常安装。

输出文件：

```text
quick_output/submission.zip
quick_output/rebuild_report.json
quick_output/validation_report.json
```

提交前必须检查：

```bash
python scripts/validate_submission.py \
  --package quick_output/submission.zip \
  --report quick_output/submission_recheck.json
```

合格条件为：

```text
SHA-256: 2e979d08d10a785e0c47a4a1ba923131a52c8e53970bb0578f815893585e8d4b
ZIP 成员: 56
顶层 USD: 34
OpenUSD/轻量物理校验: 34/34
```

快速路径不使用 GPU，也不访问网络。它的结果与已经完成线上评测的候选**字节完全相同**：本地可保证 SHA-256 一致，也就是提交的候选文件一致。在题目数据、评分规则和评测器版本不变的前提下，它对应的历史线上结果为 `67.6000`。任何未来线上分数仍由平台评测决定；本仓库不会把历史分数误写为对未来评测环境的保证。

## Baseline 亮点与得分相关设计

1. **不允许静默降级**：GPU 路径将 Shape 与 Paint 视为完整资产生成的必要步骤；纹理阶段初始化或推理失败会明确失败并保留收据，不会悄悄生成只有几何、没有纹理的候选冒充完整结果。这避免了看似成功、实际质量显著下降的提交。
2. **提交格式与物理可运行性双重校验**：校验器从提交包实际读取 USD，检查 34 个顶层资产、默认图元、纹理引用、碰撞体/刚体和物理场景，并执行 120 步轻量自由落体探测。它不能替代官方隐藏评测，但能在提交前阻断常见的格式和物理错误。

## 官方资料在代码中的使用范围

竞赛数据输入只有官方发放的 `question.zip` 与 `submission_example.zip`。代码从 `submission_example.zip` 的实际目录结构推导提交根目录，并对 `question.zip` 执行 CRC、安全路径和 34 题/视频清单检查；这些约束来自官方输入文件本身。

赛题页面、讲解回放、PPT 和论文链接只作为人工阅读资料收录在 [REFERENCES.md](REFERENCES.md)。代码不会下载、解析或把这些网页、视频、PPT 当作模型输入或检索知识库；也不会把官方原始数据、视频帧或模型缓存放入公开包。

## 路径 B：从 `question.zip` 与 `submission_example.zip` 重建

两份官方 ZIP 不随仓库分发。将其放入同一个私有目录，例如 `/data/competition_input`：

```text
/data/competition_input/question.zip
/data/competition_input/submission_example.zip
```

完整 GPU 环境和资源选择见 [GPU_BUILD.md](GPU_BUILD.md)。在已通过宿主机检查后执行：

```bash
export DATA_DIR=/data/competition_input
export OUT_DIR=/data/asset_baseline_output
export ACCEPT_HUNYUAN_LICENSE=yes

bash scripts/run_aliyun.sh
```

运行者必须先阅读并确认 SAM2 与 Hunyuan3D-2.1 的许可证允许自己的用途；脚本不会绕过这一确认。成功输出位于：

```text
$OUT_DIR/asset_baseline_submission.zip
$OUT_DIR/gpu_asset_run/manifests/
$OUT_DIR/gpu_asset_run/reports/validation.json
$OUT_DIR/gpu_asset_run/process/
```

`process/` 中的 `build_manifest.json`、`runtime.json`、`commands.jsonl`、`metrics.json` 和 `experiment_log.json` 都由运行入口生成。`manifests/` 记录输入、选帧、网格和打包过程；`reports/validation.json` 记录 34 个资产的 OpenUSD 与 MuJoCo 校验。

### 无 GPU 的代码冒烟测试

任何支持 Python 的系统都可验证输入、格式、USD 与物理链路：

```bash
asset-baseline --config config/default.yaml \
  --set question_zip=/absolute/path/question.zip \
  --set submission_example_zip=/absolute/path/submission_example.zip \
  --set output_root=outputs \
  --set run_name=cpu_smoke \
  --set reconstruction.backend=primitive \
  --set segmentation.backend=center run
```

这是一条格式和物理链路测试，不是高分承诺。macOS 与 Windows 可运行快速路径和 CPU 冒烟路径；正式 GPU 推理请在阿里云 Linux 实例中运行。Windows 可用 WSL 作为命令行替代。

## 本地测试

除 GPU 推理外，仓库中的验证均可快速执行：

```bash
pytest
```

测试覆盖：两份中间包的锁定哈希和 CRC、确定性重建、最终包的字节身份、34 个 USD 的结构与物理探测，以及从合成官方格式输入到 34 个 USD 的 CPU 冒烟流程。

## 下一步

1. 将 6 个选视角真正用于多视角一致性和纹理投影，不能只把一个视图作为条件图。
2. 使用交互视频分离可动部件，为门、抽屉、按钮和转轴生成独立碰撞体与关节。
3. 为尺度、质量、摩擦和关节限位建立任务级估计与回归测试，不把全部物体归一化为相同尺寸和质量。
4. 每次改变只生成一个独立候选，先保存本地验证和候选 SHA-256，再进行一次线上提交。

## 资料与许可证

赛题入口和课程资料链接收录在 [REFERENCES.md](REFERENCES.md)。第三方组件和模型的许可证说明在 [NOTICE.md](NOTICE.md)。
