# paper-rec

## 能力

- 从 arXiv 获取指定时间窗口内的论文
- 根据 Profile 中的研究方向进行关键词召回和分类
- 支持本地启发式排序和 Codex 语义排序
- 生成旧版风格的中文研究日报
- 输出论文、项目主页、代码仓库、作者、机构、Tags、摘要和推荐理由
- 通过飞书 Webhook 推送日报
- 使用 SQLite 记录运行状态和投递状态，避免重复发送
- 根据 arXiv 样例论文自动生成或补充 `research.yaml`

## 环境配置

### 依赖

宿主机只需要：

- Conda
- 能访问 arXiv 的网络
- 如果使用 `codex` 排序，还需要已安装并登录 Codex CLI

项目依赖已经写入 [environment.yml](environment.yml)：

- Python 3.11
- PyYAML
- pypdf（下载并解析论文 PDF）
- pytest
- 当前项目本身

### 创建环境

在项目根目录执行，Linux、macOS 和 Windows 命令相同：

```bash
conda env create -f environment.yml --override-channels -c defaults
conda activate paper-rec
```

如果环境已经存在：

```bash
conda env update -f environment.yml --prune
conda activate paper-rec
```

### `.env` 配置

复制示例文件：

Linux/macOS：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-token
PAPER_REC_RANKER=heuristic
```

程序会自动读取项目根目录下的 `.env`，不需要执行 `source .env`。

`PAPER_REC_RANKER` 支持：

- `heuristic`：默认值。本地关键词排序，不依赖 Codex，适合日常运行、离线运行和测试
- `codex`：使用 Codex 进行语义排序和中文日报编辑，输出质量更好；需要本机已安装 Codex CLI 并能连接 OpenAI API

如果 `.env` 中没有设置 `PAPER_REC_RANKER`，程序默认使用 `heuristic`。例如，切换到 Codex：

```env
PAPER_REC_RANKER=codex
```

环境变量优先级高于 Profile 中的设置。可选值只有 `codex` 和 `heuristic`。

如果使用 `codex`，先确认：

```powershell
codex exec --skip-git-repo-check --sandbox read-only "Return only []"
```

Linux/macOS 使用相同命令。Codex 必须能够连接 OpenAI API。

## Profile 制作

主 Profile 位于：

```text
profiles/research.yaml
```

主要字段：

- `id`：Profile ID，同时决定输出目录
- `title`：日报标题；使用 `customize` 后会自动更新
- `interests`：研究方向、关键词和排除词
- `sources.arxiv`：arXiv 分类、时间窗口和抓取数量
- `selection`：候选数、最低分和最大输出数量；排序器由 `.env` 的 `PAPER_REC_RANKER` 控制
- `delivery.channels`：投递渠道

### 根据样例论文生成 Profile

在 `profiles/research-seeds/` 中使用“公开模板 + 本地配置”的方式放置链接：

```text
profiles/research-seeds/
├── config.base.yaml                 # 提交到 GitHub 的默认模板
└── config.local.yaml                # 本地客制化配置，不提交
```

`config.local.yaml` 可以继承公开模板：

```yaml
inherit: config.base.yaml
mode: rewrite

interests:
  - id: spatial_intelligence
    label: 3D vision and spatial intelligence
    links:
      - https://arxiv.org/abs/2608.02580
      - https://arxiv.org/abs/2607.16187
```

本地配置中的字段会覆盖 base 配置中的同名字段；未覆盖的字段继续继承。每个方向使用 `links` 写入 arXiv 链接，每个方向最多 5 篇：

```text
https://arxiv.org/abs/2401.12345
https://arxiv.org/pdf/2402.67890.pdf
```

`config.base.yaml` 示例：

```yaml
mode: preserve
max_papers_per_interest: 5

interests:
  - id: spatial_intelligence
    label: 三维视觉与空间智能
    links:
      - https://arxiv.org/abs/1706.03762
```

个人链接直接写在 `config.local.yaml` 的 `links` 中。`.gitignore` 已经忽略该文件，因此上传到 GitHub 时只会保留 `config.base.yaml`，不会上传个人客制化内容。

`mode`：

- `preserve`：保留原有 Profile 内容，并补充或调整 interests
- `rewrite`：根据样例论文重新生成 interests，但保留 sources、selection 和 delivery 配置

执行生成：

```bash
paper-rec --root . customize --input profiles/research-seeds
```

程序会优先读取 `config.local.yaml`；如果不存在，则读取兼容旧格式的 `config.yaml`，最后读取公开模板 `config.base.yaml`。当前推荐使用 `links` 直接写链接；旧的 `file` 字段仍然兼容。

程序会访问 arXiv，调用 Codex 归纳研究方向、描述、关键词和排除词，最后写入：

```text
profiles/research.yaml
```

生成后建议校验：

```bash
paper-rec --root . validate --profile profiles/research.yaml
```

运行日报时，程序只下载最终入选论文的 PDF，解析前两页和项目主页中的链接，用于提取作者单位、项目主页与 GitHub、GitLab、Hugging Face 等代码仓库地址。PDF 或项目主页下载失败不会阻止日报生成，对应字段会显示为未获取到。

## 运行指令

以下命令在 Linux、macOS 和 Windows PowerShell 中相同，前提是已经执行 `conda activate paper-rec`，并且当前目录是项目根目录。

### 检查配置

```bash
paper-rec --root . validate --profile profiles/research.yaml
```

### 只生成日报，不发送飞书

不需要配置 `FEISHU_WEBHOOK_URL`：

```bash
paper-rec --root . run --profile profiles/research.yaml --skip-send
```

### 正式运行

```bash
paper-rec --root . run --profile profiles/research.yaml
```

输出位置：

```text
output/<profile-id>/latest.md
output/<profile-id>/<run-id>.md
```

运行和投递状态：

```text
state/paper-rec.sqlite3
```

### 手动重发

如果需要重新发送本次筛选出的论文，跳过去重检查：

```bash
paper-rec --root . run --profile profiles/research.yaml --force-send
```

该选项只影响当前运行，不会删除历史投递记录。

### 定时运行

Linux/macOS 可以使用 cron 或 systemd timer。Windows 使用“任务计划程序”，程序填写 `conda`，参数填写：

```text
run --no-capture-output -n paper-rec paper-rec --root F:\GitHub\paper-rec run --profile profiles/research.yaml
```

Linux cron 示例：

```cron
10 8 * * * cd ./paper-rec && conda run --no-capture-output -n paper-rec paper-rec --root . run --profile profiles/research.yaml >> state/cron.log 2>&1
```
