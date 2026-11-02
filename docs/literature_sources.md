# 公开文献来源与获取指南

核对日期：2026-11-02。下列入口用于发现水稻产量及相关农艺性状的研究、核对书目信息或寻找可访问的全文。**检索记录、数据库注释、可免费阅读与允许再分发是不同状态**；每篇文献仍须核对版本、来源及具体实验，不能以检索命中直接认定基因功能或因果变异。

## 文献检索与全文入口

| 来源 | 适合的用途 | 使用边界与官方说明 |
|---|---|---|
| [PubMed](https://pubmed.ncbi.nlm.nih.gov/) | 按基因、性状、作者、DOI 或关键词查找生命科学文献，利用“Free full text”和“Free in PMC”链接定位可能可读的全文。 | PubMed 主要是引文和摘要索引；出版商链接可能收费或要求机构订阅。[PubMed 介绍](https://pubmed.ncbi.nlm.nih.gov/about/)；[全文链接使用说明](https://pubmed.ncbi.nlm.nih.gov/help/#finding-the-full-text-article)。 |
| [PubMed Central（PMC）](https://pmc.ncbi.nlm.nih.gov/) | 阅读生命科学免费全文、图表和可用的补充材料；可从文献条目查看版权与许可。 | PMC 是全文归档，开放获取子集只是其中一部分；可读不等于均可用于商业重分发。[PMC 用户指南](https://pmc.ncbi.nlm.nih.gov/about/userguide/)；[版权与批量获取规则](https://pmc.ncbi.nlm.nih.gov/about/copyright/)。 |
| [Europe PMC](https://europepmc.org/) | 跨文献元数据、摘要和可用全文查找线索；可按主题检索，也可根据 PMID、PMCID、DOI 定位。 | 搜索结果并不都含全文；开放获取子集与访问、再利用许可需逐篇核对。[Articles RESTful API](https://dev.europepmc.org/RestfulWebService)；[全文与元数据范围](https://europepmc.org/docs/EBI_Europe_PMC_Web_Service_Reference.pdf)。 |
| [OpenAlex](https://openalex.org/) | 使用题名、关键词或 DOI 查找文献记录及可能的开放副本。记录中可查看 `best_oa_location`、链接、版本和许可等字段。 | 元数据及开放副本位置是发现线索，实际可访问性和许可须以目标页面为准。API 基础使用可无密钥；更大用量、分页及费用参照当时规则。[开放获取字段](https://help.openalex.org/data/works/open-access/)；[API 与认证](https://help.openalex.org/api/authentication/)。 |
| [Unpaywall DOI 查询工具](https://data.unpaywall.org/products/simple-query-tool) | 已有 DOI 时寻找开放获取状态及可能的开放副本。 | 这是定位工具，不保证所有 DOI 都有可读全文。[API 文档](https://data.unpaywall.org/products/api)规定 DOI 查询需提供使用者自己的联系邮箱；原关键词 `search` 端点已于 2026-09-18 退役，可使用 OpenAlex 搜索。不要把个人邮箱或密钥写入公开仓库。 |
| [Crossref Metadata Search](https://search.crossref.org/) | 根据题名、作者或 DOI 核对书目、出版信息，以及部分更正、许可和全文链接元数据。 | Crossref 主要提供其登记成员提交的元数据，不是全文仓库；链接可能需要其他权限。[Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)；[全文链接说明](https://www.crossref.org/documentation/retrieve-metadata/text-and-data-mining/)。 |
| [DOAJ](https://doaj.org/) | 按关键词查找开放获取期刊和论文记录，进入对应出版商页面。 | DOAJ 是目录与文章索引；仍须检查具体文章、图表的许可及第三方内容声明。[DOAJ 介绍](https://doaj.org/about/)；[文章元数据说明](https://doaj.org/docs/faq/)。 |
| [bioRxiv](https://www.biorxiv.org/) | 寻找较新的植物生物学预印本及其公开版本。 | 预印本发布时未经期刊同行评议；标明版本并检查是否存在正式发表版或修订，不能把同一研究的不同版本计为独立验证。[bioRxiv 官方介绍](https://www.biorxiv.org/about-biorxiv)。 |

本仓库的 Europe PMC 检索脚本只生成待审元数据；单篇获取脚本可在来源资格和访问状态已核对时请求开放全文 XML，并核验当前文章身份。它们不自动裁决文献或证明再利用许可；具体步骤见 [Agent 接手指南](agent_handoff.md)。其他平台在此列为补充入口。

## 水稻基因与文献导航

这些数据库有助于扩展基因别名、参考注释和论文线索；**基因页面、数据库标签或同源推断不是新的独立文献证据**。记录所用注释版本，回到原始论文的材料、比较、图表和端点核对。

| 来源 | 可用入口及用途 |
|---|---|
| 国家水稻数据中心 RiceData | [基因检索](https://www.ricedata.cn/gene/)可按基因符号或登录号检索，也有产量相关分类；[文献数据库](https://www.ricedata.cn/reference/)可按关键词、DOI、年份等定位文献。网站可能对部分数据服务另有条件；查看具体条款。 |
| RAP-DB | [Rice Annotation Project Database](https://rapdb.dna.naro.go.jp/)提供水稻参考基因组基因模型、文献支持的功能注释及相关资源；使用时核对参考组装和转录本。[数据库介绍](https://rapdb.dna.naro.go.jp/about/about.html)。 |
| funRiceGenes | [funRiceGenes](https://funricegenes.github.io/)汇集已表征水稻基因及文献线索；按基因或关键词找到原论文后再核对。 |
| Gramene Oryza | [Gramene Oryza](https://oryza.gramene.org/)可用于水稻基因组注释、已整理基因功能及通路导航；跨物种同源推断须与水稻实验证据分开。[Gramene 通路说明](https://news.gramene.org/pathways)。 |

## 可直接使用的检索示例

1. [在 PubMed 检索水稻、产量或粒数/粒重以及基因、等位变异或单倍型](https://pubmed.ncbi.nlm.nih.gov/?term=%28rice%5BTitle%2FAbstract%5D+OR+%22Oryza+sativa%22%5BTitle%2FAbstract%5D%29+AND+%28%22grain+yield%22%5BTitle%2FAbstract%5D+OR+%22grain+number%22%5BTitle%2FAbstract%5D+OR+%22grain+weight%22%5BTitle%2FAbstract%5D%29+AND+%28gene+OR+allele+OR+haplotype%29)。也可在结果页面使用全文筛选；筛选后的结果并不覆盖所有相关文献。
2. [在 Europe PMC 运行对应的标题/摘要检索](https://europepmc.org/search?query=%28TITLE_ABS%3Arice+OR+TITLE_ABS%3A%22Oryza+sativa%22%29+AND+%28TITLE_ABS%3A%22grain+yield%22+OR+TITLE_ABS%3A%22grain+number%22+OR+TITLE_ABS%3A%22grain+weight%22%29+AND+%28gene+OR+allele+OR+haplotype%29)。
3. 在 RiceData 基因或文献页面输入具体基因符号、别名、稳定 ID 或中文性状；用检出的 DOI 或题名再到上述文献入口寻找原文。

已有 DOI、PMID 或 PMCID 时，可运行 `python3 scripts/literature_links.py --doi "10.0000/example"`，生成多平台导航地址。这里的 DOI 是虚构格式示例；工具不联网验证文献身份、全文可用性或再利用许可。

示例只是起点：应根据研究问题补充有效穗、每穗粒数、粒重、株型、抽穗期和性状代价等同义词，并记录检索式、平台、日期和筛选范围。命中数会变化，不代表已审查论文数。当前项目排除孕穗期耐冷数据及其派生证据；按具体研究和证据范围处理，不凭单个关键词自动判定整篇文章。

## 原文、许可与引用

1. 优先以 DOI、PMID、PMCID、题名和文章版本确认身份；预印本、作者接受稿与正式出版版分别记录，不把同一实验的多处副本算作独立重复。
2. 对可读正文、图、表及附件分别核对版权和许可。商业或对外共享场景尤其需查看非商业、禁止演绎、署名要求以及第三方图片权利；许可未知时不要假定允许再分发。[Creative Commons 许可说明](https://creativecommons.org/faq/)；[PMC 版权说明](https://pmc.ncbi.nlm.nih.gov/about/copyright/)。
3. 批量获取 PMC 内容时，不要系统性抓取 PMC 主站；应按 PMC 指引使用相应文章数据集及其允许的辅助服务，并逐项遵守适用许可。[PMC 批量获取说明](https://pmc.ncbi.nlm.nih.gov/about/faq/)。其他来源也应遵守其接口、访问和再利用规则。
4. 将来源、获取状态、具体定位、证据与未决原因记入本仓库的结构化表；无全文、未审或原文未报告要分别保留。更多字段见[输入契约](input_contract.md)与[整理和复核方法](curation_workflow.md)。

## 本次可达性

本次核对了各平台可获取的官方说明；PubMed、PMC、RiceData、Crossref 和 RAP-DB 的入口可通过本次浏览工具查看。部分站点或示例检索在该工具中返回访问限制或超时，故**未确认全部站点及全文链接在本环境实时可达**；不同网络、机构授权或浏览器下的结果可能不同。
