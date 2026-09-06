# 接力约定

你在学校 4090 上继续天池 532506。开始任何改动前，完整阅读 [HANDOFF.md](HANDOFF.md)。

硬规则：

1. 母本是 `artifacts/pack28_mother.zip`（线上 66.73）。每一次提交都从解压它开始。
2. 一次只改 **1 个** USD 或 **1 张**贴图。CRC 必须只有那一个文件不同。
3. 不要整包替换成 Hunyuan / COLMAP / 开源 baseline。pack45 已经交过，线上 64.42。
4. 不要把 STS、AccessKey、token 写入仓库或回复。
5. 不要 git commit / push，除非用户明确要求。
6. 用户发来 ossutil STS 才上传；上传用 `--mode StsToken --sign-version v1 -f`。
7. 本机 GPU 不影响已上传 zip 的分数。4090 只用来生成更好的几何，贴图优先烤官方视频帧。
