# 输入与输出契约

CSV 使用 UTF-8 或 UTF-8 BOM，首行字段名及顺序与 `examples/synthetic/` 完全一致。五张表均需存在；允许只有表头。单元格空值表示未提供，具体原因放在 `notes`、`identity_note` 或来源审阅记录中；它既不表示零，也不表示阴性。若必须区分不同缺失原因，请在备注写明。每次构建指定一个新的输出目录。

| 表 | 键和主要内容 |
|---|---|
| `genes.csv` | `gene_id` 唯一；`symbol`、`species` 必填；记录身份依据，不按别名自动合并 |
| `sources.csv` | `source_id` 唯一；`title` 必填；可记 DOI、版本、原资产 SHA-256、可访问状态及 `scope`。哈希留空表示未知，非空须为 64 位小写十六进制 |
| `events.csv` | `event_id` 唯一并引用 `gene_id`；保留原始描述、来源类型、分子单位及已知坐标；未知坐标留空 |
| `claims.csv` | `claim_id` 唯一；引用来源、基因及可选事件；记录端点、比较、材料、环境、效应、单位、来源位置、判断及复核状态 |
| `relations.csv` | `relation_id` 唯一；引用两个事件及一个来源；保留关系类型、审阅状态和定位，不自动合并 |

`scope` 为 `eligible` / `unresolved` / `excluded`。`origin` 为 `natural` / `engineered` / `unknown`。`kind` 为 `snp` / `indel` / `sv` / `cnv` / `complex` / `haplotype` / `other` / `unknown`。`position` 如填写须为正整数，**必须在备注或来源协议中说明组装及坐标制**；缺组装不会被程序补全，也不能据此连接参考基因组。

`evidence_level` 为 `gene_functional` / `molecular_functional` / `association_only` / `allele_supported` / `event_causal` / `unresolved`。除 `gene_functional` 和 `unresolved` 外需指定事件；`event_causal` 还需指定 `trait` 与 `causal_unit`。`review_state` 为 `reviewed` / `pending` / `conflict` / `excluded`；`reviewed` 的命题须有端点和来源位置。`independent_review` 为 `pass` / `fail` / `pending` / `not_performed`，由用户填写，程序不会核验复核回执或身份。

事件关系 `relation` 为 `same_event` / `distinct_event` / `component_of` / `duplicate_representation` / `unresolved`。仅检查来源为 `eligible` 且 `review_state=reviewed` 的 `same_event` 和 `distinct_event` 是否形成冲突；待定与被排除的关系保存在库中，不参与这一检查。`component_of` 有方向：左侧为组成部分，右侧为整体。程序不传递该关系作为相等，也不将其分解为单点效应。

## 导出语义

| 视图 | 内容 |
|---|---|
| `natural_causal` | 已审、合格来源中，被录入为 `event_causal` 且来源类型为自然的事件；因果单位可能是单倍型，不能直接当作单点 QTN |
| `natural_allele` | 自然等位或单倍型支持 |
| `natural_association` | 自然事件关联候选 |
| `molecular_or_engineered` | 分子功能端点或工程事件；可与其他视图重叠 |
| `functional_gene` | 基因功能证据 |
| `unresolved` | 来源未决、命题待审/冲突、独立复核未完成或失败、证据等级未决，以及自然来源不明的事件 |
| `excluded_history` | 来源或命题标记为排除的历史记录 |

自然/工程之外的来源不自动变为自然。独立复核为 `not_performed` 的已审记录仍可按录入等级进入对应视图；所有视图保留这一字段。`pass` 是使用者提供的标签，不是机器认证的科学结论。`possible_duplicate_dois.csv` 只是导航提示；不同版本及不同实验不能由 DOI 自动合并。源数据和所有关系都保存在 SQLite 内，查询结果包括未决及排除历史，请逐行查看状态。

注释筛选输入为 `gene_id,symbol,phenotype` 三列。规则读取 `config/trait_rules.csv`，识别类似 `千粒重(TO:0000382)` 的来源字符串；其结果只是候选。穗数的有效状态未知，分蘖数、粒宽和结实率等代理不自动转换为目标性状的实测值。
