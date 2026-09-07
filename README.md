# 实验室助手（Lab Assistant）

🧪 面向化学、药学类专业大学生的本地知识库问答桌面应用。

导入你的课程资料（实验讲义、药典通则、SOP、课件等），用自然语言提问，AI 依据资料回答并**标注引用原文出处**，点击引用即可逐字核对——杜绝"一本正经胡说八道"。

## ✨ 功能特性

- **知识库问答**：内置 QC 检验知识库框架 + 自建课程知识库（支持 txt / pdf / docx）
- **引用原文对照**：每个结论后带引用编号 [n]，点击展开原文段落与出处（文件名、分类、相似度）
- **多轮追问**：结合上下文理解"它""该法"等指代（追问自动改写为完整查询）
- **防幻觉设计**：只依据检索资料回答，查不到明确说"资料中未找到相关内容"（零命中时不调用大模型）
- **笔记导出**：一键把当前对话 + 引用原文导出为 Markdown / Word，方便写实验报告
- **召回调试**：内置检索调试视图（查看命中片段与相似度分数，排查"资料里有却答不出"）
- **多知识库管理**：按课程建库、增量索引（文件哈希跳过未变化文件）、"全部"模式跨库检索
- **数据全本地**：文档、索引、对话历史全部保存在本机；无服务器、无云存储

## 🚀 快速开始（Windows 开发运行）

> 打包版安装包见 Releases（Windows，解压即用）。

```bash
# 1. 安装 Python 3.12+（勾选 Add to PATH）
# 2. 克隆代码
git clone https://github.com/yuyuyuuyuyuy/lab-assistant.git
cd lab-assistant

# 3. 创建虚拟环境并安装依赖
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# 4. 配置大模型 API Key（阿里云百炼，按量计费约 1~2 分/次问答）
#    在项目根目录新建 local_key.txt，把 Key 粘进去（不要提交到 git）

# 5. 启动
venv\Scripts\python main.py
```

首次启动时填写或跳过 API Key 向导；内置知识库会随启动自动建立索引。

### 导入自己的资料

- **内置库**：把 txt / pdf / docx 放进 `res/builtin_kb/docs/`（建议按分类建子文件夹），启动后自动（增量）建索引；
- **自建库**：应用左侧「＋」新建知识库 → 选择文件或整个文件夹。

> 注意：本仓库**不含**《中国药典》等受版权保护的语料内容（原演示语料仅内部学习使用）。请自行导入你有权使用的资料，并遵守相关版权规定。

## 📦 打包分发

```bash
build\build_win.bat   # 生成 dist\LabAssistant\（onedir 模式），压缩成 zip 即可分发
```

- Windows 10+ 需系统已装 [Edge WebView2 运行库](https://developer.microsoft.com/microsoft-edge/webview2/)（多数机器已自带）
- 未做商业签名，杀毒软件可能提示，选"仍要运行"即可
- macOS 版待发布（需在 macOS 环境构建）

## 🛠 技术栈

| 层 | 选型 |
|---|---|
| 桌面壳 | pywebview（Windows: Edge WebView2 / macOS: WKWebView） |
| 后端 | Python + Flask（本地线程，无外部服务） |
| 前端 | 原生 HTML/CSS/JS 单页（无构建工具、无 CDN） |
| 向量存储 | sqlite-vec（单文件，含块/向量/哈希表） |
| 大模型 | 阿里云百炼 qwen-plus（对话）+ text-embedding-v4（向量化），OpenAI 兼容协议 |
| 文档解析 | PyMuPDF / python-docx / charset-normalizer |
| 打包 | PyInstaller onedir |

```
app/
├── main.py            # 入口：Flask 线程 + 桌面窗口
├── config.py          # 路径与默认设置
├── backend/           # server(路由) chat(编排) search ingest kb store
│                      # embeddings parser vector_store export
├── prompts/           # 防幻觉系统提示词
├── frontend/          # 纯静态前端
├── res/               # 图标 + 内置语料目录
├── tests/             # 20 题验收问题集与测试脚本
└── build/             # PyInstaller 打包配置
```

数据目录：Windows `%APPDATA%\LabAssistant\`（设置、对话历史、各知识库索引）。

## 📄 许可证

[MIT](LICENSE) © 2026 wibecoding

## ⚠️ 免责声明

本软件仅用于学习与内部演示。问答内容由大模型基于你导入的资料生成，**正式实验与合规场景请以原始文献/标准原文为准**。请勿导入涉密资料；问答时检索到的文档片段会发送至你配置的大模型服务商用于生成回答。
