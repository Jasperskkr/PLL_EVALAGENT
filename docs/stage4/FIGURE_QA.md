# Stage4 频率响应图审查

范围：工程研究审查图，英文标注。输入为本次实际事件仿真复数返回比；不以M1曲线生成M2数据。Nominal、保存的Agent、PM边界各一列，幅频/相频各一行；UGF标记明确为局部诊断，正式周期UGF/PM仍UNKNOWN。

最终目录：`experiments/stage4_figures_20261105_02`。PDF/SVG为矢量，PNG为300dpi预览；作图源CSV、对齐结果和碰撞报告同时交付。初版目录`..._01`保留对数轴minor标签碰撞及修正前证据。

- Python/matplotlib生成；通过本地`nature-figure`静态审查工具检查并实际查看PNG。
- 静态规则18 PASS、3 WARN、0 FAIL。WARN为PNG而非TIFF、300而非600dpi及对数保护检测器未识别代码中的显式断言；不是期刊投稿格式验收。
- 最终PDF最小字号7pt；碰撞检查0 FAIL、0 WARN；对齐PASS。
- 无数据排除。低频注入、独立Clamp与M1均来自保存的原始数值；两种端口定义的局限见方法报告。

图及CSV数据在后续有效性审核中没有改变；当前根CSV与最终`stage4_summary_20261105_05`逐字节一致。作图脚本为`tools/plot_stage4.py`，QA脚本目录由`--qa-scripts`参数显式传入，不作为运行时依赖。
