# 代码来源与分享版范围

此仓库依据已有水稻产量基因先验整理流程制作，删除了固定机器路径、账户信息、运行调度、项目专属引用与数据。分享版使用相对路径和显式参数，示例完全虚构。

| 分享版 | 对应既有流程与处理方式 |
|---|---|
| `config/trait_rules.csv`、`scripts/screen_candidates.py` | 保留早期 RiceData 三要素索引的 TO 规则和直接/代理定义；重新实现可传入 CSV 的筛选及未匹配记录台账 |
| `scripts/search_europe_pmc.py`、`scripts/prepare_sources.py` | 依据现有 Europe PMC 发现流程改写为有页数上限、逐页哈希、来源行定位的独立入口；不包含全文获取及原有本地语料 |
| `scripts/acquire_fulltext.py` | 将先前的受监督测试思路改写为可配置单篇入口；在当前文章 `article-meta` 中检查 DOI 和 PMCID，保留访问停止及失败状态 |
| `scripts/extract_jats_evidence.py`、`scripts/local_model_review.py`、`scripts/validate_review.py`、回执复验工具 | 根据受监督模型测试的问题编写段落/图注提取、受限本地调用和候选检查；结果一律待独立科学复核，不声称具备无人值守资格 |
| `scripts/literature_links.py` | 为本分享版新增的离线导航工具；由使用者提供 DOI、PMID 或 PMCID，不自动取得全文或认证这些标识属于同一文献 |
| `scripts/claim_task_key.py` | 从已有 QTN 待办键规则抽出六字段、规范 JSON 和 SHA-256 的算法，用于定位具体增量命题 |
| `scripts/build_prior.py`、`scripts/query_prior.py` | 根据现有来源/基因/事件/比较/证据分层和只读查询原则编写简化分享版；并非内部数据库或发布脚本的直接复制 |

内部工作流还包括来源资产及哈希绑定、逐命题历史回执、独立审阅回执、事件与比较的增量发布、多个消费视图和项目专用数据接口。上述生产功能并未全部移植；本仓库的结构校验或合成测试通过，不等于内部发布验收、文献审阅完成或结果已获验证。需要复用内部已有数据库时应单独设计并核验转换程序，不能直接将其当作此处输入。
