# Agent 接手与故障处理

## 当前能力与边界

仓库提供候选检索、单篇 Europe PMC 开放全文 XML 获取、来源身份检查、单篇本地 Ollama 调用、引文机械检查、证据分层与回执复验。各步骤可由 Agent 按任务合同顺序调用；**它们不是已验收的一键无人值守批处理系统**。未在本版完成长时稳定性、断电、监督器被杀、真实限流或本地模型服务崩溃后的恢复测试。

前期受监督测试曾出现模型输出截断、引文连字符空格误拦截、图注不含方向而模型给出方向、遗传对照背景遗漏等情况。另有单篇对照暴露身份混淆和将“不显著”扩写为“无代价”。这些观察不构成模型总体排名；本版的规则只能提示部分风险，不能证明其余结果正确。已有来源及结论的报告权限仍按适用政策处理，**机器检查状态不是科学报告门禁**。

## 开始前

1. 固定问题、纳入与排除范围、来源版本、任务 ID、预期产物和审阅范围。按 DOI 及别名查询当前访问停止记录与已有资产；在有停止记录时可复用范围合格且哈希已核对的持有资产，但不得换路线继续获取同一来源。保留撤稿、综述、排除和身份未决状态。
2. 使用新目录与足够磁盘空间，按实际机器确定线程、内存、时限和进程树监督。仓库的单次调用不启动或管理模型服务；小时级或无人值守运行需要另行验收的在线监督、取消清理、检查点及中断恢复能力。
3. 确认本地模型服务和模型文件身份及许可。脚本只接受数字回环 HTTP 地址，拒绝模型目录中明确标为远程的条目，并比较服务报告的模型摘要；这仍不能单凭服务响应证明后端绝不转发或模型文件真实未变。不要把非公开资料发送到未获授权的外部服务。
4. 本仓库的样例、DOI、材料、模型名及效应均为虚构。以下 `/tmp` 路径每次必须替换为新目录；源文件与输出应留在适用存储位置，不提交到公开仓库。

## 1. 检索与预审

运行 README 中的 `search_europe_pmc.py` 和 `prepare_sources.py`；搜索命中只作线索。查询输出目录的 `manifest.json`：`partial` 说明未证明覆盖全集；`access_stop` 表示限流、访问拒绝或验证页面，停止该来源/路径并记录处理条件；`failed` 是其他错误，不应当作无结果。不要用其他域名、工具或网络路线绕过访问停止。

补齐来源身份、DOI、PMCID、物种、撤稿或更正、研究范围及访问状态后，再决定是否获取。结构化清单中的 `scope` 和 `access_status` 是调用方的审阅结论，程序不会连接项目的实时来源或停止注册表；Agent 必须在发起请求前核对这些记录，不能自行把未知写成允许。

## 2. 获取或复用全文

从 [source_preflight.json](../examples/synthetic/source_preflight.json) 复制一份至私有工作区。合格的单篇任务需要 `doi`、`pmcid`、`scope: eligible`、`access_status: allowed` 和 `open_access: true`；示例故意保持未决，不应直接用于网络获取。`open_access` 是上游元数据判断，仍要逐篇核对许可及实际文件身份。

```bash
python3 scripts/acquire_fulltext.py --source private/source.json --out runs/acquisition_001
```

脚本只对 Europe PMC 的指定 PMCID 发起一次直接 HTTPS 请求，不自动重试或改用其他来源。它在 XML 的**当前文章 `article-meta`**中核对 DOI 和 PMCID，并检查正文；参考文献中的 DOI 不可替代文章身份。`valid_fulltext_xml` 仅表示传输、身份与基本结构合格，不表示图表、许可或科学结论已核验。

`access_stop`、`source_not_eligible`、`invalid_source`、`invalid_asset`、`source_changed`、`code_changed`、`transport_failed` 和 `redirect_requires_review` 都不是成功；已写入的 `.partial` 与 `acquisition_receipt.json` 保留。若进程被强制杀死或磁盘耗尽导致没有回执，人工/Agent 检查文件与实际进程终态，再使用新目录重试，不能把 partial 当作完整资产。

## 3. 准备证据与本地模型任务

对已核验的 JATS XML，可按下列方式提取正文段落与图注文本；另有合格转写时，也可按同一格式准备输入：

```bash
python3 scripts/extract_jats_evidence.py --source private/source.xml \
  --doi '替换为真实DOI' --pmcid '替换为真实PMCID' --out runs/extract_001
```

`evidence.json` 包含与源文件哈希绑定的段落锚点、章节路径、图注标签及未提取的表格/图片计数。提取仅覆盖正文中的 `p` 元素；非 `p` 图注、原图像素、表格单元格和补充材料不提取，上下标及公式可能被扁平化。应据具体命题决定是否回看原图/原表。输出的 `coverage` 保守标为 `selected_paragraphs`，不是全文审阅完成。Agent 如需缩小输入，应另存证据文件并登记所选和未选锚点，不得静默丢失上下文。

输入 JSON 的 `source_sha256` 为原始资产哈希，`coverage` 为 `selected_paragraphs` 或 `complete_transcript`，`anchors` 将稳定段落定位映射到文本。参照 [model_evidence.json](../examples/synthetic/model_evidence.json)。全文覆盖标签及原文到转写的对应是**使用者的声明**，模型调用程序只核对哈希和字段，不自动证明转写正确。

复制 [model_task.json](../examples/synthetic/model_task.json) 到私有工作区，填入真实任务、模型名、服务报告摘要、源资产和证据文件 SHA-256、上下文/输出/线程/时限预算，以及正确的数字回环端口。源的 `scope`、`identity_status`、`held_asset_verified` 和 `access_status` 均须来自实际核验。样例模型摘要为虚构值，不能直接用于真实模型。

```bash
python3 scripts/local_model_review.py \
  --task private/model_task.json --evidence runs/extract_001/evidence.json \
  --asset private/source.xml --out runs/model_attempt_001
```

单次调用会记录请求、原始响应、输入和代码哈希、模型服务报告的摘要、证据范围及校验回执。请求设置 `truncate=false`、`shift=false`；实际服务是否支持并正确执行需按其版本独立验证，不能仅凭请求字段声称输入未截断。任务文本视为待分析数据，提示词也不能保证模型不受文献内容中的指令影响。此入口不自动下载模型、不启动进程、不选择远程模型，也不回退代理。

## 4. 检查与定向复核

离线演示不需要启动模型：

```bash
python3 scripts/validate_review.py \
  --response examples/synthetic/model_response.json \
  --evidence examples/synthetic/evidence_anchors.json \
  --out /tmp/rice_prior_review_example
```

`review_receipt.json` 分开记录完成状态、机械检查和 `PENDING_INDEPENDENT_REVIEW`。仅空白和字母/数字两侧连字符空格做受限归一化，不删除连字符或替换数字、方向和组名。引文输入可为锚点到文本的 JSON，或保留 `anchor_map` 的提取结果；后者可提示图注证据仍需查看原图。引文命中只证明相应字符串出现；风险标记用于转交复核，**没有标记不证明结论正确**。方向、对照、样本/收获单位、表格与图像、原文冲突和模型自己补写的背景都须按命题核对。

`output_truncated`、`incomplete_response`、`invalid_json`、`invalid_schema`、`citation_or_schema_failure` 和服务错误不是完成。截断时保留原回应及旧任务，增加输出预算前确认上下文与资源。可在新任务 JSON 中填写 `"retry_of": {"receipt": "旧运行/run_receipt.json", "sha256": "已独立记录的旧回执哈希"}`，仅提高 `limits.output_tokens`，并使用新目录重新调用。程序复验旧回执、源资产、证据、代码、已记录的模型标识和原任务，并在新调用前检查服务报告的模型摘要；问题、上下文、证据及其他设置变化会被拒绝。同一截断链最多一次此类重试，不自动重跑；若需改变问题、选段、模型或其他参数，按新版本任务记录范围变化及关系，不能把更窄结果当成原任务完成。不得因一个模型或规则未发现问题而跳过独立复核。

## 5. 交接和复用

保存运行目录、任务和输入路径、各项 SHA-256、模型摘要、覆盖范围、状态、风险与精确下一步。回执与输入之间的哈希没有签名；其预期哈希应在另一个可信清单中记录。复用前核验哈希和当前代码：

```bash
python3 scripts/verify_review.py --receipt runs/review_001/review_receipt.json --sha256 '<已记录的回执SHA256>'
python3 scripts/verify_local_run.py --receipt runs/model_attempt_001/run_receipt.json --sha256 '<已记录的回执SHA256>'
```

前者复算引文检查，后者还核对任务、源资产、证据、请求、原始回应及嵌套验证回执。`REUSE_CANDIDATE_ONLY` 只代表记录一致且可继续审阅，不表示科学结论、当前来源许可或当前模型状态已重新核实。失败或截断回执只能作诊断。提交到正式先验前按 [输入契约](input_contract.md) 和 [整理与复核方法](curation_workflow.md)完成具体命题的独立审阅与身份审查；不从模型结果直接生成已审记录。

## 开发检查

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖引用归一化、方向提示、访问停止、全文身份、模型长度异常、篡改与部分中断；多数为合成数据及模拟服务。可选外部接口的真实连通、完整论文审读和长时间运维不能由此推定通过。Ollama 参数语义与版本变化见 [Ollama API 定义](https://github.com/ollama/ollama/blob/main/api/types.go)；源站访问规则见 [公开文献与资源入口](literature_sources.md)。
