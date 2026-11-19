# HLODBuilder v1.0

入口：Unity 菜单 `Moonflow/HLOD Builder`。Houdini 22.0.466 后端位于 `build_proxy.py`。

此仓库仅包含 Houdini 后端。安装 Houdini 22.0.466 和 SideFX Labs 后，在 Unity 插件的「环境配置 / 清理」中选择本机 hython.exe 与本仓库根目录，并点击验证。Unity 编辑器及运行时在 MoonflowSystem 的 HLODBuilder 分支单独维护。Jobs、场景资产及历史 Tests 目录不随仓库分发。可在仓库根目录用 hython smoke_test.py 运行独立的减面冒烟测试。

## 自动模式

- 一个实际模型：取已有 LODGroup 的最低有效网格继续减面，保留原材质；生成独立远景代理，原 LODGroup 不改动。
- 多个实际模型：走完整 HLOD。选中一个含多个模型的父节点仍属于对象集。LODGroup 算一个模型；没有 LODGroup 的多部件 prefab 按实例归组。
- 自动检查并开启模型资产 Read/Write；顶点色只警告、忽略并继续。

## 最短操作

1. 选中对象集（可多选，也可选共同父节点）。打开窗口，点击“使用当前选中对象集”。
2. 设置基础块尺寸、层级数、保留面数和图集分辨率，点击“分析选区 / 预览分块”。窗口显示实际模型数与模式；Scene 视图画出各块内容包围盒。
3. 点击“自动生成”。工具导出选区，后台启动本机 hython，完成后自动回导；状态栏显示当前减面/烘焙阶段，可取消。
4. 选中生成的 `__MF_HLOD_Tree`，用 Preview 的 Originals / LeafProxies / CoarsestProxies 对照原物体、叶块和父块，恢复 Automatic 后按相机距离切换。

已有旧代理时先用“移除生成的场景 HLOD（保留资产）”，再重新选取源对象集生成。删除生成树同样恢复原物体；资产保留便于检查。

## 完整流水线

按世界坐标 XZ 网格自动归组 → 每层块内各模型 PolyReduce → 合并网格 → UV Unwrap / UV Layout → SideFX Labs Maps Baker 原生高低模烘焙 → 回导网格、PBR 图集、URP/Lit 材质 → 建立父子 HLOD 树。

上层网格尺寸每级翻倍，保留面数比例每级减半。较大对象按中心归属块，保持整个对象，不切断网格。每块的不透明与 AlphaTest 分开合并，通常产生一到两个代理材质。保留 Albedo、Normal、Metallic、Smoothness、Opacity、AO、Emission；AO 是源材质遮蔽通道的转烘焙，不是重新计算环境遮蔽。

每台相机独立选择层级，父块显示时隐藏其全部源对象且不显示子块；相机结束恢复原 Renderer 状态。原 LODGroup、切换阈值不修改。未实现磁盘流式加载或卸载，优化目标为远景渲染负载。

## 输出与排查

- Unity：`Assets/HLODGenerated/Build_<任务ID>/` 保存每块网格、材质和图集。
- Houdini：`F:\Projects\Houdini\HLODBuilder\Jobs\<任务ID>\` 保存 `job.json`、`progress.json`、`result.json`、`build.log`、`proxy.hip`、输入几何和烘焙贴图。
- 用 Houdini 打开 `proxy.hip` 可直接查看各层块的减面、UV、合并和 Maps Baker 节点。
- 完成状态的“三角形总计”是所有层资产总和，不是同一帧绘制量。

## 当前输入范围

MeshRenderer（无需勾选 Unity Static），完整 HLOD 支持 Gamma / Linear 色彩空间，输出 URP/Lit 材质。导出器按当前项目处理底色和自发光，不修改项目色彩空间设置。支持 Standard / URP Metallic PBR 属性映射、不透明和 AlphaTest；自定义 Shader 仅映射同名标准属性，不复现风动画、顶点色、特殊光照、细节混合。暂不接受透明混合、蒙皮/Billboard 末级、Specular 工作流、MaterialPropertyBlock、已经绑定 Lightmap 的 Renderer。所选低级模型的 Layer、阴影与 Rendering Layer 需一致；不同通道使用不同 UV 缩放偏移需专门适配。失败时不会隐藏源场景。

这是一套可检查的编辑器构建与运行时层级切换流水线，并非任意 Shader 的通用渲染捕获器。

对象不需要勾选 Unity Static，工具也不会修改 Static 标记。生成代理是源网格及相对变换的快照；生成后若改变源对象相对于代理根节点的位置、旋转、缩放或网格，应重新生成。源对象与代理随共同父节点整体移动不受此限制。

## Shader 属性映射

在 HLOD Builder 中展开“Shader 属性映射（自动识别 / 手动指定）”：

1. 点击“读取对象集材质”，从下拉列表选取参考材质；也可直接拖入材质。
2. 查看 Shader 和“当前解析”。底色自动识别 `_BaseMap`、`_MainTex`、`_Diffuse`、`_Albedo`、`_DiffuseTex`、`_AlbedoMap`、`_BaseColorMap` 等；法线识别 `_BumpMap`、`_NormalMap`、`_Normal` 等。
3. 有多个有效候选或自定义名字时，从该 Shader 的真实属性下拉列表中选择。列表按 2D 贴图、颜色、数值筛选，不读取材质文件中旧 Shader 遗留的字段。
4. “其他 PBR 通道”可配置金属、光滑、AO、自发光、裁切阈值和开关；自定义 Shader 不使用 `_EMISSION` 关键字时，可明确启用自发光模式。AlphaTest 也可明确启用/禁用。
5. 修改自动保存于 `ProjectSettings/MFHLODShaderMappings.asset`，按 Shader 资产关联，作用于该项目中使用同一 Shader 的材质。可点击“重置此 Shader 为自动识别”。建议将配置文件纳入版本管理。

“不使用（默认值）”能显式关闭某通道映射；底色不使用时以白色底图与乘色生成纯色。贴图属性存在但未赋贴图时会警告并使用默认值，不自动迁移旧属性中的资源。

当前通道打包仍为金属度 R、光滑度 A、AO G；法线要求 Unity Normal Map 约定。该面板映射基础 PBR 参数，不自动复制自定义 Shader 的渐变、层混合、风、顶点数据和特殊光照计算。`BK/VegetationLeaves` 可识别 `_Diffuse`、`_Normal`、`_MainColor`、`_NormalPower`，其完整视觉逻辑仍需专用烘焙适配。
## 多材质公共候选映射

无需指定参考材质即可在各通道直接输入候选名，以 `;` 分隔，例如底色 `_BaseMap;_MainTex;_Diffuse;_Albedo`，法线 `_BumpMap;_NormalMap;_Normal`。可点击“填入常用候选属性”。每个 submesh 仍使用其 sharedMaterials 中对应的材质独立解析，不以参考材质替换整个选区。

公共候选优先于 Shader 专属配置；留空则沿用专属配置或自动识别。按顺序过滤不存在或类型不匹配的属性；贴图优先选择已赋贴图的第一个候选，否则选第一个有效属性。数值/颜色使用第一个有效属性。底色全部不匹配会报出具体材质；其他可选通道无匹配时使用默认值。`-` 明确禁用该通道。候选不是把多个贴图相乘或混合。

## 任务进度与 Scene 状态

生成时自动使用本次真实分块计划绘制 Gizmos：灰色等待、橙色当前块、绿色已完成、红色失败、紫色取消。当前块标出 ID 和步骤。重新分析选区清除任务着色，恢复青色叶级/黄色父级预览。

面板分别显示已完成块数、当前块已完成步骤数、当前步骤耗时及进程 CPU 活动。每个不透明/裁切桶分为构建节点、减面计算、UV、保存工程、主 PBR、AO、自发光和网格导出八步。步骤进度不是耗时比例，原生烘焙内部没有可用的真实百分比；运行中动画和进程存活也不能证明烘焙正常推进。长时间无 CPU 活动可辅助排查，不能单独判定死锁。

stdout/stderr 持续写入任务目录 build.log，带接收时间，不再等待进程结束。面板可打开任务日志目录。验证：Unity 6000.0.23f1 引用编译通过，Houdini 22.0.466 三块/两层、含不透明和裁切桶的实际烘焙通过，最终进度3/3，输出298三角形。未自动验收用户场景中的 Gizmos 画面。

## UV算法更新（2026-11-17）

详见同目录 [UV_OPTIMIZATION.md](UV_OPTIMIZATION.md)。已改用 Auto Seam + UV Flatten + UV Layout；增加独立UV子进程超时、失败时有上限拆页、完成块检查点与多尺寸像素风险报告。原来“每块通常1–2材质”不再是硬上限：失败拆页会增加材质、贴图和绘制批次，默认每类最多4页。

生成前可设“计划最小贴图尺寸”。默认同烘焙尺寸；若后续要缩小，应事先设定对应尺寸。工具按该尺寸保留8像素间距预算，但不会保证亚像素小岛或全部mipmap画质。报告中 spacingBudgetSupported 不能当作画质通过。风险结果会在完成信息提示，制作小尺寸版本前必须检查报告与实际画面。
