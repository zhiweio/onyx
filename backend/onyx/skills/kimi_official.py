"""Official Kimi skills shipped in the Craft gallery.

Selected from the public mirror https://github.com/haomingz/kimi-skills to
match Kimi's published agent-skill categories, plus the nine tool skills
that ship with MoonshotAI/kimi-cli:

- https://www.kimi.com/resources/content-writing-skills-for-agents
- https://www.kimi.com/resources/academic-skills-for-agents
- https://www.kimi.com/resources/report-writing-skills-for-agents
- https://www.kimi.com/resources/graphic-skills-for-agents
"""

from __future__ import annotations

from typing import Final, NamedTuple

from onyx.db.enums import SystemCatalogCategory


class KimiOfficialSkill(NamedTuple):
    slug: str
    name: str
    description: str
    category: SystemCatalogCategory
    tags: tuple[str, ...]


def _skill(
    slug: str,
    name: str,
    description: str,
    category: SystemCatalogCategory,
    *extra_tags: str,
) -> KimiOfficialSkill:
    tags = ("kimi", category.value.lower().replace("_", "-"), *extra_tags)
    return KimiOfficialSkill(
        slug=slug,
        name=name,
        description=description,
        category=category,
        tags=tags,
    )


KIMI_OFFICIAL_SKILLS: Final[tuple[KimiOfficialSkill, ...]] = (
    # ── content writing ──────────────────────────────────────────────────
    _skill(
        "ad-copywriter",
        "广告文案",
        "广告创意写作，适配主流付费广告平台的标题、描述与完整方案。",
        SystemCatalogCategory.CONTENT,
        "copy",
    ),
    _skill(
        "campaign-planner",
        "营销活动策划",
        "完整营销活动策划，含目标、受众、渠道、内容日历与效果指标。",
        SystemCatalogCategory.CONTENT,
        "campaign",
    ),
    _skill(
        "copy-editor",
        "文案精修",
        "七轮专业编辑优化营销文案，润色表达而不从零重写。",
        SystemCatalogCategory.CONTENT,
        "copy",
    ),
    _skill(
        "marketing-writer",
        "营销文案",
        "撰写或优化首页、落地页、定价页等页面文案，提升转化。",
        SystemCatalogCategory.CONTENT,
        "copy",
    ),
    _skill(
        "seo-copywriting-guide",
        "SEO 文案",
        "按 12 步工作流生成 SEO 文章，含标题、Meta、FAQ 与自评清单。",
        SystemCatalogCategory.CONTENT,
        "seo",
    ),
    _skill(
        "ecom-copy-assistant",
        "电商详情文案",
        "生成淘宝、京东、亚马逊商品详情页标题、卖点、规格与 FAQ。",
        SystemCatalogCategory.CONTENT,
        "ecommerce",
    ),
    _skill(
        "wechat-post-craft",
        "公众号文章",
        "撰写微信公众号文章，覆盖标题、排版规范与引流 CTA。",
        SystemCatalogCategory.CONTENT,
        "wechat",
    ),
    _skill(
        "xhs-note-creator",
        "小红书笔记",
        "小红书笔记全流程创作，并渲染生成图片卡片。",
        SystemCatalogCategory.CONTENT,
        "xiaohongshu",
    ),
    _skill(
        "zhihu-viral-answer",
        "知乎回答",
        "按故事、干货、金句结构生成知乎高赞回答。",
        SystemCatalogCategory.CONTENT,
        "zhihu",
    ),
    _skill(
        "short-video-script",
        "短视频脚本",
        "按 Hook、冲突、反转、CTA 结构写抖音与短视频脚本。",
        SystemCatalogCategory.CONTENT,
        "video",
    ),
    _skill(
        "podcast-blueprint",
        "播客脚本",
        "生成含开场、分段话题、预设问题与收尾 CTA 的播客脚本。",
        SystemCatalogCategory.CONTENT,
        "podcast",
    ),
    _skill(
        "video-outline-planner",
        "视频策划",
        "规划视频选题、结构与互动话术。",
        SystemCatalogCategory.CONTENT,
        "video",
    ),
    _skill(
        "html-email-builder",
        "HTML 邮件刊",
        "生成兼容 Gmail 与 Outlook 的 HTML Newsletter。",
        SystemCatalogCategory.CONTENT,
        "email",
    ),
    _skill(
        "html-mail-builder",
        "HTML 邮件模板",
        "生成欢迎、促销、通知、订单确认等场景的响应式邮件。",
        SystemCatalogCategory.CONTENT,
        "email",
    ),
    _skill(
        "rhetoric-speech-craft",
        "演讲稿",
        "按修辞三角撰写发布会、年会或 TED 演讲稿，并嵌入舞台提示。",
        SystemCatalogCategory.CONTENT,
        "speech",
    ),
    _skill(
        "humanizer-zh",
        "去 AI 痕迹",
        "检测并修复常见 AI 写作模式，使文本读起来更自然。",
        SystemCatalogCategory.CONTENT,
        "editing",
    ),
    _skill(
        "audience-adapter",
        "向上汇报",
        "按 CEO、VP、技术或运营受众调整粒度、语气与侧重点。",
        SystemCatalogCategory.CONTENT,
        "communication",
    ),
    _skill(
        "pro-email-composer",
        "商务邮件",
        "按催办、跟进、拒绝、感谢等场景生成得体中英文商务邮件。",
        SystemCatalogCategory.CONTENT,
        "email",
    ),
    _skill(
        "customer-reply-craft",
        "客服话术",
        "为售前、售后、投诉与退换货生成回复，含情绪安抚策略。",
        SystemCatalogCategory.CONTENT,
        "support",
    ),
    _skill(
        "lp-proto-gen",
        "落地页原型",
        "一键生成含 Hero、社会证明、功能、定价与 CTA 的落地页原型。",
        SystemCatalogCategory.CONTENT,
        "landing",
    ),
    # ── academic ─────────────────────────────────────────────────────────
    _skill(
        "research-writer",
        "研究写作",
        "支持资料调研、补充引用、开头优化、大纲梳理与逐节反馈。",
        SystemCatalogCategory.ACADEMIC,
        "writing",
    ),
    _skill(
        "research-advisor",
        "科研顾问",
        "协助选题、项目规划与问题排查，输出研究方案与风险评估。",
        SystemCatalogCategory.ACADEMIC,
        "research",
    ),
    _skill(
        "research-paper-refiner",
        "论文润色",
        "按学术写作标准审查语法、用词、语态与逻辑衔接。",
        SystemCatalogCategory.ACADEMIC,
        "writing",
    ),
    _skill(
        "paper-review-coach",
        "论文评审",
        "模拟同行评审，从原创性、方法论、结果与写作四维度分析论文。",
        SystemCatalogCategory.ACADEMIC,
        "review",
    ),
    _skill(
        "ref-style-converter",
        "参考文献格式",
        "在 APA、MLA、IEEE、Harvard 之间转换并校验参考文献。",
        SystemCatalogCategory.ACADEMIC,
        "citation",
    ),
    _skill(
        "xindaya-translator",
        "信达雅翻译",
        "按信达雅原则做中英双向翻译，覆盖学术、商务、技术与法律。",
        SystemCatalogCategory.ACADEMIC,
        "translation",
    ),
    _skill(
        "flashcard-studio",
        "记忆闪卡",
        "从学习材料提取知识点，生成可导入 Anki 的闪卡。",
        SystemCatalogCategory.ACADEMIC,
        "study",
    ),
    _skill(
        "bloom-quiz-maker",
        "布鲁姆出题",
        "按布鲁姆六层认知分类生成选择题、简答题与案例题。",
        SystemCatalogCategory.ACADEMIC,
        "quiz",
    ),
    _skill(
        "sci-paper-cn",
        "顶会论文",
        "按 CVPR、NeurIPS、ACL 等顶会惯例撰写、排版与打磨论文。",
        SystemCatalogCategory.ACADEMIC,
        "paper",
    ),
    _skill(
        "regression-insight",
        "回归分析",
        "对表格数据做线性或逻辑回归，输出系数、R²、p 值与解读。",
        SystemCatalogCategory.ACADEMIC,
        "stats",
    ),
    _skill(
        "corr-insight",
        "相关分析",
        "计算 Pearson、Spearman 与偏相关，识别可能的伪相关。",
        SystemCatalogCategory.ACADEMIC,
        "stats",
    ),
    _skill(
        "speech-synthesis",
        "语音合成",
        "把文字转为多语言、多音色语音，并输出字幕。",
        SystemCatalogCategory.ACADEMIC,
        "tts",
    ),
    # ── report writing ───────────────────────────────────────────────────
    _skill(
        "equity-researcher",
        "投研报告",
        "生成 A 股、港股、美股投资速览或深度研报。",
        SystemCatalogCategory.REPORT,
        "equity",
    ),
    _skill(
        "equity-research-report-cn",
        "卖方研报",
        "按卖方研究视觉风格撰写股票、行业或策略研报。",
        SystemCatalogCategory.REPORT,
        "equity",
    ),
    _skill(
        "equity-earnings-review",
        "财报点评",
        "撰写卖方股票财报点评，含 EPS、指引、估值与电话会要点。",
        SystemCatalogCategory.REPORT,
        "earnings",
    ),
    _skill(
        "stock-research-report-cn",
        "证券研究报告",
        "按国泰海通或海通国际风格撰写个股与行业跟踪报告。",
        SystemCatalogCategory.REPORT,
        "equity",
    ),
    _skill(
        "investment-memo",
        "投资备忘录",
        "撰写风投交易备忘录或宏观主题备忘录。",
        SystemCatalogCategory.REPORT,
        "investment",
    ),
    _skill(
        "market-insight-report",
        "市场洞察报告",
        "生成含高管摘要、趋势分析与战略建议的市场洞察报告。",
        SystemCatalogCategory.REPORT,
        "market",
    ),
    _skill(
        "primary-market-research",
        "一级市场研究",
        "撰写 PE/VC 一级市场行业研究报告。",
        SystemCatalogCategory.REPORT,
        "pe-vc",
    ),
    _skill(
        "commodity-research-outlook",
        "大宗商品展望",
        "按卖方惯例撰写能源、金属或农产品展望与交易建议。",
        SystemCatalogCategory.REPORT,
        "commodity",
    ),
    _skill(
        "work-report-writer",
        "周报月报",
        "从工作记录或 git log 生成周报或月报。",
        SystemCatalogCategory.REPORT,
        "work",
    ),
    _skill(
        "meeting-recap",
        "会议纪要",
        "把会议记录整理为议题、结论与带负责人的行动项。",
        SystemCatalogCategory.REPORT,
        "meeting",
    ),
    _skill(
        "sop-writer",
        "SOP 文档",
        "把业务流程写成含流程图、RACI 与异常处理的 SOP。",
        SystemCatalogCategory.REPORT,
        "sop",
    ),
    _skill(
        "okr-planner",
        "OKR 规划",
        "协助制定、拆解、对齐与复盘 OKR。",
        SystemCatalogCategory.REPORT,
        "okr",
    ),
    _skill(
        "workload-calculator",
        "工时估算",
        "用三点估算、T-shirt sizing 或功能点分析估算项目工时。",
        SystemCatalogCategory.REPORT,
        "estimate",
    ),
    _skill(
        "iteration-planner",
        "Sprint 规划",
        "按团队产能完成 Sprint 范围、拆分、依赖与负载均衡。",
        SystemCatalogCategory.REPORT,
        "agile",
    ),
    _skill(
        "legal-risk-analyzer",
        "法律风险评估",
        "按严重性与发生概率评估法律风险，并给出行动建议。",
        SystemCatalogCategory.REPORT,
        "legal",
    ),
    _skill(
        "competitive-seo-intel",
        "竞品 SEO 分析",
        "分析竞品关键词、内容打法、外链与 AI 引用模式。",
        SystemCatalogCategory.REPORT,
        "seo",
    ),
    _skill(
        "astro-observation-report-cn",
        "引力波观测报告",
        "按 Physical Review X 双栏风格撰写引力波观测结果论文。",
        SystemCatalogCategory.REPORT,
        "science",
    ),
    # ── graphic ──────────────────────────────────────────────────────────
    _skill(
        "code-to-chart",
        "代码架构图",
        "解析代码依赖并生成架构图、流程图或组织架构图。",
        SystemCatalogCategory.GRAPHIC,
        "diagram",
    ),
    _skill(
        "data-viz-gen",
        "数据信息图",
        "从 JSON 生成自包含 HTML 或 SVG 信息图与仪表盘。",
        SystemCatalogCategory.GRAPHIC,
        "chart",
    ),
    _skill(
        "chart-gen",
        "图表生成",
        "从 JSON 生成折线、柱状、K 线或热力图等图表。",
        SystemCatalogCategory.GRAPHIC,
        "chart",
    ),
    _skill(
        "database-inspector",
        "数据库探查",
        "只读探查 SQLite 或 PostgreSQL，并生成 Mermaid ER 图。",
        SystemCatalogCategory.GRAPHIC,
        "database",
    ),
    _skill(
        "ui-blueprint",
        "UI 设计系统",
        "从 UI 截图提取配色、字体、组件与间距，生成实现提示词。",
        SystemCatalogCategory.GRAPHIC,
        "ui",
    ),
    _skill(
        "fashion-sketch-cn",
        "服装技术规格",
        "创建含规格、尺寸表、面料库与 BOM 的服装 Tech Pack。",
        SystemCatalogCategory.GRAPHIC,
        "fashion",
    ),
    _skill(
        "geo-magazine-slides-cn",
        "地理杂志幻灯片",
        "创建地理杂志风格的演示文稿，含大幅主图与数据图表。",
        SystemCatalogCategory.GRAPHIC,
        "slides",
    ),
    _skill(
        "journalistic-portrait-cn",
        "人物周刊排版",
        "复刻人物周刊视觉风格的中文杂志 HTML 版面。",
        SystemCatalogCategory.GRAPHIC,
        "magazine",
    ),
    _skill(
        "photo-magazine-cn",
        "杂志级报告",
        "用大字排版、满版摄影与数据卡片制作杂志级报告。",
        SystemCatalogCategory.GRAPHIC,
        "magazine",
    ),
    _skill(
        "retro-tech-illustration-cn",
        "复古科技插画",
        "创建 Synthwave、Vaporwave 或 Cyberpunk 风格的视觉内容。",
        SystemCatalogCategory.GRAPHIC,
        "illustration",
    ),
    _skill(
        "theme-kit",
        "主题样式箱",
        "为演示文稿、文档或 HTML 页面提供预设或自定义主题。",
        SystemCatalogCategory.GRAPHIC,
        "theme",
    ),
    # ── kimi-cli tool skills ─────────────────────────────────────────────
    _skill(
        "codex-worker",
        "并行 Codex 代理",
        "通过 tmux 并行启动和管理多个 Codex CLI 代理。",
        SystemCatalogCategory.DEV_TOOL,
        "kimi-cli",
    ),
    _skill(
        "feature-smoke-test",
        "功能冒烟测试",
        "为新增或变更功能规划并执行可重复的端到端冒烟测试。",
        SystemCatalogCategory.DEV_TOOL,
        "kimi-cli",
    ),
    _skill(
        "gen-changelog",
        "Changelog 生成",
        "为代码变更生成规范化的 Changelog 条目。",
        SystemCatalogCategory.DEV_TOOL,
        "kimi-cli",
    ),
    _skill(
        "gen-docs",
        "文档更新",
        "更新 Kimi Code CLI 用户文档。",
        SystemCatalogCategory.DEV_TOOL,
        "kimi-cli",
    ),
    _skill(
        "gen-rust",
        "Python 到 Rust 同步",
        "把 Python 变更同步到 Rust 实现，跳过 UI 与登录相关部分。",
        SystemCatalogCategory.DEV_TOOL,
        "kimi-cli",
    ),
    _skill(
        "pull-request",
        "创建 Pull Request",
        "创建并提交 GitHub Pull Request。",
        SystemCatalogCategory.DEV_TOOL,
        "kimi-cli",
    ),
    _skill(
        "release",
        "发布工作流",
        "执行 Kimi Code CLI 包的发布工作流。",
        SystemCatalogCategory.DEV_TOOL,
        "kimi-cli",
    ),
    _skill(
        "translate-docs",
        "双语文档同步",
        "翻译并同步双语文档。",
        SystemCatalogCategory.DEV_TOOL,
        "kimi-cli",
    ),
    _skill(
        "worktree-status",
        "Git worktree 审计",
        "审计当前项目的 git worktree，标出可安全清理的工作树。",
        SystemCatalogCategory.DEV_TOOL,
        "kimi-cli",
    ),
)

KIMI_CLI_SKILL_SLUGS: Final[frozenset[str]] = frozenset(
    skill.slug
    for skill in KIMI_OFFICIAL_SKILLS
    if skill.category is SystemCatalogCategory.DEV_TOOL
)
