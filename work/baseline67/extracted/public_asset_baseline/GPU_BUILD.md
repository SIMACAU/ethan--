# 阿里云 GPU 构建指南

本文只描述从 `question.zip` 与 `submission_example.zip` 重新生成资产的 GPU 路径。快速精确复现不需要 GPU，见 [README.md](README.md)。

## 资源选择与结论

优先选择运行 Linux 的阿里云 GPU ECS：

| 用途 | 实例 | GPU | CPU / 内存 | 系统盘 |
|---|---|---|---|---|
| 最小兼容宿主机 | `ecs.gn8is.2xlarge` | 1 × NVIDIA L20，48 GiB | 8 vCPU / 64 GiB | 500 GiB ESSD |
| 完整生成推荐 | `ecs.gn8is.4xlarge` | 1 × NVIDIA L20，48 GiB | 16 vCPU / 128 GiB | 500 GiB ESSD |

两档均使用 Ubuntu 22.04 x86_64、Docker 和 NVIDIA Container Toolkit，并允许首次安装时临时访问公开代码、模型和 Python 依赖源。`ecs.gn8is.2xlarge` 足以承载单卡 L20 的完整软件栈；`ecs.gn8is.4xlarge` 为视频解码、模型编译和资产校验保留更多 CPU/内存余量，作为公开 Baseline 的默认推荐。

阿里云当前规格表将 `ecs.gn8is.2xlarge` 列为单张 L20、48 GiB 显存、8 vCPU 和 64 GiB 内存，并将 `ecs.gn8is.4xlarge` 列为同一张 L20、16 vCPU 和 128 GiB 内存。[阿里云 GPU ECS 规格说明](https://help.aliyun.com/zh/ecs/user-guide/gpu-accelerated-compute-optimized-and-vgpu-accelerated-instance-families-1) 控制台可用地域和库存可能变化，应以实际购买页为准。

**边界说明：**上述规格与容器要求兼容，且仓库在启动前会检查 GPU、显存、磁盘、Docker 和容器内 GPU 可见性；这能证明宿主环境满足基线的硬件前提。它不等同于“当前第三方模型版本已经在每个地域完整推理成功”——模型下载、许可、驱动和上游依赖仍需由一次实际运行验证。不要在未通过预检时静默换成 24 GiB 显存卡运行完整 Shape + Paint 路径。

## 容器与网络要求

| 项目 | 基线值 |
|---|---|
| 操作系统 | Ubuntu 22.04 x86_64 |
| 网络 | 允许临时访问公开代码、模型和 Python 依赖源 |
| 容器 | Docker + NVIDIA Container Toolkit |

## 安全与宿主机验收

1. 只开放 SSH 所需的最小安全组规则，并把来源限制为操作者公网 IP。
2. 不把私钥、账号 Cookie、临时下载令牌或官方原始数据提交到仓库。
3. 使用带 GPU 驱动的 Ubuntu 22.04 镜像，创建后先执行：

```bash
git clone <YOUR_PRIVATE_OR_PUBLIC_REPOSITORY_URL> public_asset_baseline
cd public_asset_baseline
bash infra/verify_gpu_host.sh
```

脚本必须打印 GPU 名称、显存、驱动版本、Docker 版本和可用磁盘空间，并成功在容器中运行 `nvidia-smi`。它要求至少 45,000 MiB 显存和 200 GiB 可用磁盘；失败时先修复驱动、磁盘或 NVIDIA Container Toolkit，不要启动模型安装或推理。`scripts/run_aliyun.sh` 也会自动运行该预检，避免漏做。

阿里云驱动版本会随镜像或资源选择变化。CUDA 容器使用 `12.4.1`；需保证宿主 NVIDIA 驱动与此容器兼容。NVIDIA Container Toolkit 的安装说明以其[官方文档](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)为准。

## 输入准备

将从赛题页面获得的两份官方 ZIP 放在私有目录：

```text
/data/competition_input/question.zip
/data/competition_input/submission_example.zip
```

不要把这两个文件、解压视频、帧、掩码或模型缓存纳入公开分享包。首次运行前确认 Hunyuan3D-2.1 许可证允许当前用途；该项目不会替你作许可判断。

## 运行

```bash
export DATA_DIR=/data/competition_input
export OUT_DIR=/data/asset_baseline_output
export ACCEPT_HUNYUAN_LICENSE=yes

bash scripts/run_aliyun.sh
```

该入口会先执行宿主机预检，再构建容器，固定公开依赖的源码提交，下载所需模型，并将模型缓存挂载在仓库的 `third_party/`。后续重跑复用该缓存，但每个 `OUT_DIR` 应是新的空目录，避免混淆过程收据。

## 完成门槛

运行结束后，至少检查：

```bash
cat "$OUT_DIR/gpu_asset_run/reports/validation.json"
cat "$OUT_DIR/gpu_asset_run/process/metrics.json"
```

前者应显示 `valid: true`、`valid_tasks: 34` 和 `simulation_steps: 120`。后者应保存 ZIP SHA-256。然后单独保留整个 `gpu_asset_run/`，而不是只保留最终 ZIP。

GPU 推理本身不在轻量测试范围内；完整运行前需通过宿主机验收，运行后需通过上述 34 题验证报告。生成候选是否接近快速路径的线上表现，必须由独立线上评测确认。
