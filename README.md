# RiceYield Prior

## 项目简介

RiceYield Prior 面向作物育种和遗传研究中分散的文献证据，整理水稻产量相关基因、自然变异和功能先验。项目将来源、基因、分子事件、材料与对照、性状效应及审阅状态连接起来，帮助研究团队追溯候选依据、识别背景差异和性状代价，并为后续群体分析与实验设计准备可核查的先验。

本仓库提供可移植的候选筛选、来源登记、证据整理、校验与查询脚本，适合公司研发团队和科研同事了解方法、共享标准及在自有数据上试用。**代码不自动证明因果，也不包含真实的项目数据库。**

*RiceYield Prior organizes literature-based evidence on rice yield genes, variants and traits into a traceable, reviewable workflow for research and breeding teams.*

[完整项目介绍](docs/project_overview.md) · [公开文献与资源入口](docs/literature_sources.md)

## 工作流程

```mermaid
flowchart LR
    A[数据库注释与文献线索] --> B[候选筛选和来源登记]
    B --> C[核验原文、图表与材料]
    C --> D[逐事件、比较及性状录入证据]
    D --> E[独立复核增量与身份关系]
    E --> F[结构校验、SQLite 与分层视图]
    F --> G[按基因查询及下游使用]
```

| 环节 | 本仓库可运行的部分 | 人工完成或外部提供 |
|---|---|---|
| 候选召回 | RiceData 风格表型中的 TO 编号与三类产量构成规则匹配；保留未匹配行和直接/代理标签 | 提供有使用权的注释数据；补充产量、株高、抽穗期及其他相关性状，不能将这组三要素规则当成全库范围 |
| 文献发现 | Europe PMC 元数据分页检索、保存回执和生成待审来源表 | 冻结检索范围和日期，筛查物种、主题、撤稿/更正、权利及原文身份 |
| 原文获取与模型候选 | 单篇合格 Europe PMC XML 获取、身份核对、段落/图注提取、本地模型单次调用、引文检查与哈希回执 | 事先核对来源资格及停止记录；监督模型服务，审查图表、方向、对照及科学结论 |
| 证据提取 | 提供字段、稳定任务键、参考模板与表结构 | 阅读决定性正文、图表及补件，记录材料、对照、环境、端点、正反结果与精确位置 |
| 事件关系和审阅 | 检查键、引用、字段、已审的同一/不同事件关系冲突 | 裁决事件是否相同，区分自然等位、工程扰动、单点、单倍型和基因功能；独立复核实质性增量 |
| 数据库与查询 | 创建 SQLite、七类证据视图、重复 DOI 提示、哈希清单和分页查询 | 对照真实来源复核结论、定位、空值及许可；按目标项目定义下游分析合同 |

候选筛选、人工审阅、独立复核、软件检查是不同步骤。标题命中、来源条目、工程检查通过或记录数增加，均不能单独证明基因功能或分子事件因果。不同论文、不同端点和多个图表也不自动等于独立重复实验。

## 环境与快速运行

需要 Python 3.9 及以上，脚本只使用标准库。以下命令在仓库根目录运行；输出目录必须是**尚不存在**的新目录。示例基因、来源、变异、效应和复核状态均为虚构，**不是科研结果**。

```bash
python3 scripts/screen_candidates.py \
  --input examples/synthetic/annotations.csv \
  --out /tmp/rice_prior_screen_example

python3 scripts/build_prior.py \
  --input-dir examples/synthetic \
  --out /tmp/rice_prior_build_example

python3 scripts/query_prior.py \
  --db /tmp/rice_prior_build_example/prior.sqlite \
  --gene DEMO1 --limit 10

python3 scripts/claim_task_key.py examples/synthetic/review_task.json
python3 -m unittest discover -s tests -v
```

筛选产出 `candidate_annotations.csv` 与覆盖所有输入行的 `screening_ledger.csv`。入库产出 `prior.sqlite`、七个 `view_*.csv`、`possible_duplicate_dois.csv` 和 `manifest.json`；视图可以重叠，不能将行数相加解释为独立事件数。未决与排除历史仍保留。失败时新运行目录保留 `failure.json`，完成目录不能原地覆盖。

## Agent 接手

[Agent 接手与故障处理](docs/agent_handoff.md) 提供来源准入、单篇原文获取、本地模型候选、失败状态、重试与回执复验的步骤。仓库也提供 [AGENTS.md](AGENTS.md) 作为协作约束。模型及检索结果保持候选状态，程序无法替代独立科学审阅；单次入口尚未验收为长时间无人值守系统。

## 可选：检索文献元数据

此步骤需要网络，仅保存检索元数据，不下载全文、不绕过访问限制。页数上限是明确的工作预算；`partial` 表示未证明覆盖全部命中。用不同的新目录保存每次检索。

```bash
python3 scripts/search_europe_pmc.py \
  --query '(TITLE_ABS:rice OR TITLE_ABS:"Oryza sativa") AND ("grain yield" OR "grain number")' \
  --max-pages 2 --out /tmp/rice_prior_search_example

python3 scripts/prepare_sources.py \
  --search-dir /tmp/rice_prior_search_example \
  --out /tmp/rice_prior_source_intake_example
```

待审 `sources.csv` 默认全部为 `scope=unresolved`；需结合论文版本、撤稿信息、原文及当前研究范围逐条确认后，才能作为正式整理输入。`source_record_lineage.csv` 保留每个检索记录对应的页、行和哈希。`metadata_conflicts.csv` 单列同一来源记录的标题或 DOI 差异。接口说明见 [Europe PMC Articles RESTful API](https://dev.europepmc.org/RestfulWebService)。

## 为一篇文献生成多来源链接

已知 DOI、PMID 或 PMCID 时，可离线生成 DOI、Crossref、OpenAlex、PubMed、PMC 和 Europe PMC 的相应导航链接：

```bash
python3 scripts/literature_links.py --doi '10.0000/example'
```

上面的 DOI 仅作格式示例，不代表真实论文。也可使用 `--pmid` 和 `--pmcid`；多个标识符必须由使用者核实属于同一文献。生成链接不会联网检查文献是否存在、是否开放或是否允许再分发。来源选择和使用范围见 [公开文献与资源入口](docs/literature_sources.md)。

## 用自己的数据

复制 [examples/synthetic](examples/synthetic/) 的五张结构化表为工作区模板，维护来源、基因、分子事件、逐命题证据及事件关系；字段与状态说明见 [输入契约](docs/input_contract.md)。样例 `annotations.csv` 是另一条候选筛选支路，不自动写入证据表。数据格式是本分享版的简化接口，**不能直接当作内部生产数据库 schema 或验收回执**。

推荐的科学判断原则和版本管理见 [整理与复核方法](docs/curation_workflow.md)。其他文献与开放全文线索见 [公开文献与资源入口](docs/literature_sources.md)；项目来源及分享版与内部流程的差异见 [代码来源与范围](docs/provenance.md)。

## 发布边界

仓库仅包含代码、方法说明和虚构示例，不含项目材料/基因型/表型、内部数据库、全文 PDF、个人目录、访问凭据或聊天及调度记录。私有输入和运行目录由 `.gitignore` 排除；发布任何新增文件前仍须核对内容、访问权、敏感信息和第三方再分发许可。仓库尚未指定代码许可证，复用和再分发权限请向仓库所有者确认。
