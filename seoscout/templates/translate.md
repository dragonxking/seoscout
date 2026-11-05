<!--
变量（由 translate.py 自动注入）：
- $language_name   : 目标语言名称（如 Spanish、Japanese）
- $lang_code       : 目标语言代码（如 es、ja）
- $content         : 待翻译的英文 MDX 文章内容
-->

将以下 MDX 内容从英文翻译为 $language_name。

重要规则：
1. 将所有文本内容自然、流畅地翻译为 $language_name
2. 保持所有 Markdown 格式不变（标题 ##、列表 -、加粗 **、链接 []、表格等）
3. 保持所有 HTML 标签和 MDX 组件标签不变（Steps、Step、CodeList、CodeItem、CopyCode、Keybinds、Keybind、Callout、Cycle、CycleStage、Checklist、CheckItem、FAQList、FAQItem、FAQ、YouTubeEmbed、CardGrid、Card、Section）
4. 保持组件的 prop 名不变；只翻译人类可读的 prop 值（title、action、reward、status、question、children）。不要翻译 code、keys、type、videoId、lastChecked、checked、href
5. 保持所有 URL 不变
6. 保持文章结构和长度一致

元数据翻译规则：
- title：必须翻译为 $language_name
- description：必须翻译为 $language_name
- summary：必须翻译为 $language_name（如存在）
- 其他所有元数据字段保持不变（category、date、lastModified、image 等）
- 元数据块必须保持 JavaScript export 格式，不得使用 YAML frontmatter（---）

目标语言：$language_name ($lang_code)

英文原文：

$content

关键输出规则：
1. 仅输出翻译后的 MDX 内容，不要添加任何其他文字
2. 直接以 `export const metadata = {` 开头 — 不要使用 YAML frontmatter（---）
3. 不要将输出包裹在代码块中
4. 不要添加任何解释或说明
5. 输出必须是有效的 .mdx 文件，包含 JS export 元数据 + Markdown 正文
