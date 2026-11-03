# RiceYield Prior

RiceYield Prior 面向水稻遗传与育种研究，整理产量相关基因、自然变异和性状的文献先验。项目将文献来源、基因、分子事件、材料与对照、性状效应和审阅状态组织为可追溯的证据，帮助研究团队共享知识、梳理候选并支持后续研究设计。

*RiceYield Prior organizes literature-based evidence on rice yield genes, variants and traits into a traceable, reviewable workflow.*

[项目介绍](docs/project_overview.md) · [公开文献来源](docs/literature_sources.md) · [Agent 接手指南](docs/agent_handoff.md)

## 工作流程

```mermaid
flowchart LR
    A[基因注释与文献发现] --> B[候选筛选和来源登记]
    B --> C[原文获取、定位与证据提取]
    C --> D[基因、事件、比较和性状整理]
    D --> E[审阅与独立复核]
    E --> F[SQLite 和分类视图]
    F --> G[基因查询与后续研究]
```

| 环节 | 项目提供的工具与产物 |
|---|---|
| 候选筛选 | 依据 TO 编号筛选产量构成相关注释，记录直接性状、代理性状及筛选台账 |
| 文献发现 | Europe PMC 分页检索、来源登记、记录谱系及元数据冲突提示 |
| 原文与模型 | 单篇 Europe PMC XML 获取、文章身份核对、段落和图注提取、本地模型候选及引文定位 |
| 证据整理 | 来源、基因、分子事件、逐项命题和事件关系的结构化模板 |
| 构建与查询 | 关系检查、SQLite 构建、七类证据 CSV、基因分页查询及哈希清单 |

来源、对照、研究条件、性状端点和审阅状态随记录保留。模型候选结合原文、图表和独立复核形成可使用的文献证据。

## 文献接口与来源

| 来源 | 项目中的使用方式 |
|---|---|
| Europe PMC | 脚本直接检索元数据，并可按来源资格获取单篇开放全文 XML |
| Crossref、OpenAlex | 根据 DOI 生成元数据及开放获取线索链接 |
| PubMed、PMC | 根据 DOI、PMID 或 PMCID 生成检索和文章页面链接 |
| Unpaywall、DOAJ、bioRxiv 等 | 在[公开文献来源](docs/literature_sources.md)中提供导航和使用说明 |

不同入口的具体支持情况及测试记录见[接口清单](docs/literature_sources.md#项目接口与导航清单)。

## 环境与快速运行

使用 Python 3.9 及以上版本，脚本使用 Python 标准库。下例使用虚构数据演示候选筛选、数据库构建与查询；每次运行使用新的输出目录。

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

筛选结果包括 `candidate_annotations.csv`、`screening_ledger.csv` 和运行清单。建库结果包括 `prior.sqlite`、七类 `view_*.csv`、`possible_duplicate_dois.csv` 和 `manifest.json`。各视图保留来源和复核状态，支持按研究用途选择。

## 检索与来源登记

```bash
python3 scripts/search_europe_pmc.py \
  --query '(TITLE_ABS:rice OR TITLE_ABS:"Oryza sativa") AND ("grain yield" OR "grain number")' \
  --max-pages 2 --out /tmp/rice_prior_search_example

python3 scripts/prepare_sources.py \
  --search-dir /tmp/rice_prior_search_example \
  --out /tmp/rice_prior_source_intake_example
```

来源登记表记录待审条目、分页谱系及元数据冲突。后续可依据论文版本、研究范围和原文内容补充来源状态。检索 API 说明见 [Europe PMC Articles RESTful API](https://dev.europepmc.org/RestfulWebService)。

## 文献链接导航

提供 DOI、PMID 或 PMCID 后，可生成相应来源的导航链接：

```bash
python3 scripts/literature_links.py --doi '10.0000/example'
```

示例 DOI 用于展示格式。实际使用时填写已核对的文章标识，并结合文献页面查看版本与获取信息。

## 使用自己的数据与交接

以 [examples/synthetic](examples/synthetic/) 中的五张表为模板，整理来源、基因、分子事件、具体命题和事件关系。字段说明见[输入契约](docs/input_contract.md)，整理原则见[整理与复核方法](docs/curation_workflow.md)。

[Agent 接手指南](docs/agent_handoff.md)提供来源预审、全文获取、本地模型候选、运行记录、复核和故障处理步骤；[代码来源](docs/provenance.md)说明分享版与既有流程的对应关系。
