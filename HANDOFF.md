# 4090 接力说明书（天池 532506）

给学校电脑上的 AI：先读完本文再动代码。这是 2026-08 至 2026-09-06 在家里 RTX 3060 Laptop（6GB）上的全部有效实验。仓库主人会把你接到 24GB 4090 上做高质量重建。

- 比赛：[2026-具身仿真合成挑战赛](https://tianchi.aliyun.com/) 入口 ID **532506**
- 队伍：爱拼才会赢 / 澳门大学
- 工作区根目录：本仓库（原路径 `C:\Users\MACAU\Desktop\天池`）
- 对话历史很长，以本文和 zip 字节为准，不要凭印象改母本

---

## 1. 你现在要做什么

**目标：** 在 4090 上做「几何用重建、贴图用官方视频帧」的高质量重建，但 **禁止整包替换**。正确做法是：

1. 解压 `artifacts/pack28_mother.zip` → 得到 `submission/item_XXX/`
2. 只换 **1 个** `item_XXX.usd`（必要时连带该物体自己的 textures）
3. 其余 33 件从 pack28 **原样拷回**
4. Blender 渲染对照官方外观视频首帧
5. 打 zip，CRC 应 **仅目标文件不同**
6. 用户给 STS 后再上传。每天最多 **3 次**。榜保留历史最高，掉分不会覆盖 66.73

4090 上 Hunyuan3D-2.1 必须 **sequential**（先 Shape 卸掉，再 Paint）。官方 Shape+Paint 常驻要约 29GB，resident 模式是给 48GB L20 的。24GB 配置见 `work/baseline67/extracted/public_asset_baseline/config/default.yaml` 里的注释：`hunyuan_load_mode: sequential`。

**不要因为有 4090 就重跑开源整包。** 那份字节我们已经交过。

---

## 2. 赛制（不要再查错）

| 项 | 值 |
|---|---|
| 任务 | 真实物体视频 → 可仿真 USD（几何、材质、部件、关节、碰撞、物理） |
| 评测 | 服务端 VLM 按 rubric 打分，**不看你本机 GPU** |
| 每天提交 | 最多 3 次 |
| 榜 | 保留历史最高 |
| 初赛 A | 到 2026-09-21 |
| 初赛 B | 2026-09-22–24 |
| 合成 | A 40% + B 60%，前 30 晋级 |
| 上传 | ossutil + STS，凭证 **1 小时**，zip 覆盖同名 `ossFileName` |
| 官方前缀形态 | `oss://tianchi-race-upload/result/race/532506/1839/1376110/1095281185104/<时间戳>_ossFileName` |

上传命令（Windows，凭证由用户当场给，**禁止写入本仓库**）：

```text
ossutil.exe cp <local.zip> oss://tianchi-race-upload/result/race/532506/1839/1376110/1095281185104/<时间戳>_<名字>.zip ^
  -i <AK> -k <SK> -e oss-cn-hangzhou.aliyuncs.com -t <STS> ^
  --mode StsToken --sign-version v1 -f
```

家里 ossutil：`tools/ossutil/ossutil-2.3.0-windows-amd64/ossutil.exe`  
文档：<https://help.aliyun.com/document_detail/50452.html> 与 <https://help.aliyun.com/document_detail/120057.html>

---

## 3. 母本（必须守住）

**pack28 = 66.73**（2026-08-31 出分），当时榜约第 11。

- 仓库内：`artifacts/pack28_mother.zip`
- 原桌面：`C:\Users\MACAU\Desktop\pack28.zip`（应与上面同内容）
- 备份名：`output/submission_pack28_juice_handle.zip`

内容特征：参数化几何 + **视频首帧/反照率贴图** + 关节/物理。  
已证涨分点：**item_002 果汁箱顶部透明环提手**（视频里有，形状对，不是黑方块）。

交包规则永远是：

```text
解压 pack28
  → 只改 1 个 USD（优先 USD 手术，不要用当前 scripts 全量重建）
  → 贴图从 pack28 原样拷回（除非这次实验就是换这一张贴图）
  → CRC 只应目标文件不同
```

`scripts/blender_build_item.py` + `scripts/asset_catalog.py` **已经偏离 pack28 USD**。不要用它们全量打 34 件再交。

---

## 4. VLM 真正认什么（所有实验的总教训）

1. VLM 更认「**官方视频帧糊在方块上**」（颜色/图案对得上）。人眼更像实物的纯色重建或扫描网格经常掉分。
2. 真正涨过的：外形几乎不动时，加一个 **视频里明确存在、形状也对** 的零件（果汁提手是透明环）。
3. 往 USD 上贴视频里没有的小零件会被当多余部件扣分（假黑块、假银块、假挂孔）。
4. 评测端常见：LLM JSON 解析失败、402、runner 143 —— **不是几何分**，但占当天次数。
5. **本机有没有 GPU、是 3060 还是 4090，都不改变已经上传的 zip 的分数。** 同一份 pack28 在哪台机器交都是 66.73。

---

## 5. 成绩对照（相对 pack28 = 66.73）

| 包 | 改动 | 分数 | 结论 |
|---|---|---|---|
| pack16 | 空心碗/杯/薯片罐等历史线 | 65.83 | 被 pack28 取代 |
| **pack28** | pack16 + 果汁透明环提手 | **66.73** | **母本** |
| pack32–38 | 面包机/灯罩/刀/微波炉/床头柜等参数化乱改 | 63 以下或 JSON 失败 | 冻 |
| pack39/40 | 笔记本/鼠标去贴图改纯色 | 402 | 无有效分 |
| pack41 | 一次改 6 件家具去贴图 | 62.04 | −4.69 |
| pack42–44 | 炸锅按钮/饭煲横条/显示器背板（假黑块） | 62.04 / JSON / 60.09 | 冻 |
| pack45 | 开源「67.6」原包整包交 | **64.42** | 整包换 Hunyuan 亏 −2.31 |
| pack46 | pack28 + item_022 银色挂孔/撕口 | JSON 后重传 **62.89** | −3.84，冻 022 |
| pack47 | pack28 + 只清洗 item_025 albedo（去掉黑转盘） | **63.23** | −3.50，冻 025 贴图 |

2026-09-06 榜上他人大约：中南 76.86、武大 76.52、中山 71.37、ben1234560/WPS练习生 69.25。76 分段像整包真重建，不是一次贴一个小零件能追上的。

评测有噪声：同一文件不同天可能差约 1–2 分。换母本建议 **Δ≥+1.5**；+0.5～+1.5 当候选；|Δ|<0.5 中性；Δ≤−1 回退并冻结该改法。

---

## 6. 冻结（不要再改这些）

参数化/零件/贴图实验已失败或已在母本里的：

`001–017, 020, 021, 024, 027, 028, 030–034`

另外：

- `item_002` 提手已在母本，不要再动果汁箱
- `item_022` 挂孔/撕口已证伪（62.89）
- `item_025` 清洗 albedo 已证伪（63.23）

禁止再做：

- 尺寸/轴向瞎调
- 空心再开口（罐/碗/杯已经在高分包里）
- 加关节/抽拉碰运气
- 改场景 item_033/034
- 去掉视频贴图改纯色
- 贴假黑/银方块
- 整包换开源 zip
- 把开源 `item_029`/`item_030` 整文件塞进 pack28
- 把 COLMAP/OpenMVS 原网格直接打进包（早期扫描上榜很差）

相对未单独证伪、但高风险：`018` 笔记本、`019` 鼠标。纯色重建曾 402。官方首帧笔记本是 **合盖** ThinkPad，不要强行开盖。

---

## 7. 开源 67 分 baseline（只许学方法，不许整包交）

- 仓库：<https://github.com/ben1234560/AiLearning-Theory-Applying/tree/master/EmbodiedAI/竞赛实践/2026-具身仿真合成挑战赛>
- 本地：`work/baseline67/`，Release zip `public_asset_baseline_release.zip`
- Path A（无 GPU）：底包 + 只换 `item_029`、`item_030` 两个 USD，他们锁死历史 **67.6000**
  - 候选 SHA-256：`2e979d08d10a785e0c47a4a1ba923131a52c8e53970bb0578f815893585e8d4b`
  - 我们交的 pack45 就是这份字节，线上 **64.42**
- Path B：Hunyuan3D-2.1 Shape+Paint + SAM2，文档写约 48GB L20
- 他们的提交前缀是 `submission_example/submission/`；我们 pack28 是 `submission/`
- 硬伤：大量家具无视频贴图；Hunyuan 贴图会错物体（如 item_022 贴成心相印而非物美）；item_030 贴图碎裂

可学的只有：**底包不动，一次换 1～2 个 USD，叠视频里有的零件。**  
不要把他们的 USD/贴图塞进 pack28。

---

## 8. 4090 上怎么跑重建（这才是你来的原因）

家里 3060 6GB **跑不动** Hunyuan3D-2.1 完整 Shape+Paint。项目 `.venv` 当时 **没有 torch**。

4090 24GB 可行的拆法（来自 Hunyuan 官方 README 与 baseline 配置注释）：

| 阶段 | 大约显存 | 4090 |
|---|---|---|
| Shape | ~10GB | 可以 |
| Paint | ~21GB | 可以（先卸 Shape） |
| Shape+Paint 常驻 | ~29GB | **不行**，不要 `resident` |

建议流程（**一次一个物体**）：

1. 从该物体**外观视频**抽清晰帧，SAM2 / rembg 抠前景（不要转盘、不要手）
2. Hunyuan Shape 出网格
3. **贴图优先不用 Hunyuan Paint 的编造图。** 用官方视频帧投影/烘焙到网格（VLM 认视频外观）。Paint 只当几何不够看时的备选，且必须和视频品牌/图案对得上
4. 尺度对齐 pack28 该物体 bbox（`scripts/asset_catalog.py` 里的 `size` 只是先验，以 pack28 USD 的 bbox 为准）
5. 关节/碰撞/刚体：能从 pack28 原 USD 抄就抄；抄不了就单刚体 + convexHull，不要发明视频里没有的关节
6. 只替换 pack28 里这一个 USD，渲染对照，再决定交不交

开源 GPU 入口在 `work/baseline67/extracted/public_asset_baseline/`，但那是 **34 件全生成**。你要改成单件，并强制视频贴图。不要直接 `bash scripts/run_aliyun.sh` 然后把输出当提交包。

COLMAP/OpenMVS 家里已经跑过一部分。现成带纹理 GLB：

`001, 002, 009, 013, 021, 022, 025, 026, 027`

这些扫描网格早期整包打进去分数很差。4090 若要用，必须清理浮飞、对齐尺度、**重新烤视频贴图**，并且一次只换一件。`item_025` 的扫描是糊的黑板+噪点，不要用。

摄影测量脚本：`scripts/run_photogrammetry.py`、`scripts/prepare_frames.py`、`scripts/generate_masks.py`。  
通用渲染：`work/preview_pack34/qa_item.py`（Blender：`-- item_XXX stem`）。  
USD 加零件（默认黑块，容易再演 pack42–44）：`work/preview_pack34/add_part_usd.py`。

家里 Blender：`C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`。学校按实际路径改 `qa_item.py`。

---

## 9. 目录地图

```text
item_001 … item_034/     官方每题外观+交互视频（部分 >100MB 未进 git，见第 12 节）
scripts/                 构建/抽帧/摄影测量；已偏离 pack28，不要全量重建提交
output/                  历史提交 zip 与解压目录
artifacts/pack28_mother.zip   母本
artifacts/pack45_opensource_baseline.zip  开源原包（线上 64.42）
artifacts/pack47_item025_albedo.zip       清贴图失败包（线上 63.23）
work/baseline67/         开源 67 分仓库与解压
work/photogrammetry/     COLMAP 帧/掩码/部分 GLB
work/preview_pack34/     渲染与单件打包脚本
reports/contact_sheets/  每题 12 格关键帧
tools/ossutil/           Windows 上传工具（COLMAP 安装包未进 git）
submission_example/      官方提交格式示例
```

pack28 里值得知道的未冻结项现状（几何仍是母本，不要轻易换）：

- `018` 合盖 ThinkPad + 视频贴图 + 红点/logo + 屏幕关节。官方首帧就是合盖
- `019` 缩放球体 + 滚轮/DPI/USB-C + 视频贴图
- `022` **冻**。绿膜 12 卷包装，12 个卷在盒内不外凸
- `025` **冻贴图**。盒+顶封 + 原 albedo（站立橙袋，图里带黑转盘）。VLM 要这张糊图，不要「抠干净」
- `030` 圆柱盘+两耳 + 视频帧（浅木色熊/兔脸）。开源 030 是重建+五官叠加，贴图碎裂

---

## 10. 交包流水线（PowerShell）

```powershell
$env:PYTHONPATH = "<repo>\scripts"
# 1. 解压 artifacts/pack28_mother.zip 到一个干净目录
# 2. 只改 1 个文件
# 3. 其余 textures 保持 pack28
# 4. zip 成员路径必须是 submission/item_XXX/...
# 5. CRC 对比 pack28
# 6. Blender qa_item.py 对照官方帧
# 7. 用户给 STS 且确认后再 ossutil
```

参考实现：`work/preview_pack34/build_pack46.py`、`build_pack47.py`（后者是失败实验，只学打包/CRC，不要学它的贴图清洗）。

---

## 11. 2026-09-06 停在哪

- 当天 3 次已用完：pack46 JSON 失败 → pack46=62.89 → pack47=63.23
- 用户问 GPU 会不会影响分数、要不要去学校用 4090。答案：分数看 zip；4090 只对「做出更好资产」有用
- 用户要把本仓库推到 https://github.com/SIMACAU/ethan-- 给学校 4090 的 AI 接力
- 家里 Cursor 登录的 GitHub 是 **Mikey-SI**（gh 显示 useriiiis），对 SIMACAU/ethan-- 当时只有 pull、没有 push。需要 SIMACAU 把 Mikey-SI 加成 Write，或在这台机器 `gh auth login` 换成 SIMACAU

---

## 12. 未进 git 的文件

官方 34 题视频都在家里的 `item_XXX/` 目录，**没有进 GitHub**：一次推 3GB 会被 GitHub HTTP 500 断开。学校重建请用 U 盘/网盘拷整份 `item_001`…`item_034`。

另外因单文件 100MB 限制未进 git：

- COLMAP Windows CUDA 安装包与解压目录（学校按系统自装）

`.venv/` 不要拷，学校自己建环境。

仓库里有：HANDOFF、pack28 母本、历史失败包、脚本、开源 baseline、摄影测量中间结果、渲染对照图。

---

## 13. 给 4090 AI 的第一周实验顺序（不要并行交）

每天 3 次，每包只改 1 件，出分再做下一件：

1. 选一个 **几何明显不是方块、pack28 却是简单体素** 的物体（转椅 004、落地灯 005、电热水壶 017 都是好候选）。家具 001–012 的参数化改动已经冻过，但 **「重建网格 + 视频贴图」** 还没在 4090 上单独证伪。
2. 做出后必须并排看：官方外观首帧 vs Blender 渲染。图案/颜色对不上就不要交。
3. 若第一件 Δ≤−1：冻「该物体的重建网格」，换下一件，不要叠加。
4. 若 Δ≥+1.5：把该 zip 升为新母本，再叠下一件。
5. 不要一天交 3 个不同策略的整包。

回复用户用中文。不要自动 git commit。不要在回复里回显 AK/SK/token。
