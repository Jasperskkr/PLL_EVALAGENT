# Release 文件下载与恢复

网络对长时间大文件上传不稳定，因此除已经完整上传并校验的交接包外，大附件按 32 MiB 切成 `.part001` 等传输片段。所有片段均按 GitHub 返回的 SHA256 和大小验证。`ASSET_MANIFEST.json` 描述原始完整文件，`TRANSFER_MANIFEST.json` 描述它们与实际附件片段的对应关系。

下载本 Release 的全部附件至同一目录，然后运行：

```powershell
python assemble_assets.py --downloaded C:/downloaded_release --target C:/new_assembled_assets
```

目标目录必须不存在。该脚本验证每个片段及重组后的原文件 SHA256，恢复原始十份 evidence ZIP、Stage6B 便携包、交接包及索引。片段和重组结果的字节完全一致，研究文件没有改写。

随后从已经克隆的本仓库恢复一个研究工作树（目标也必须不存在）：

```powershell
python C:/new_assembled_assets/restore_evidence.py --repo C:/PLL_EVALAGENT --assets C:/new_assembled_assets --workspace stage6b --target C:/restored_stage6b
```

`--workspace` 可选 `master`、`stage6a` 或 `stage6b`。仓库源码、报告和进度可以直接通过 GitHub 阅读；附件用于原始证据与完整复现。最终 `FINAL_SYNC_RECEIPT.json` 记录实际远端验证结果。
