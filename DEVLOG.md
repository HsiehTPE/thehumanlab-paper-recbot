# Development Log

本文件用于记录 HumanLab Paper Radar 的开发与发布进度。

当前 Beta 版与 Public 版的代码和功能保持一致。后续如果 Beta 版包含尚未公开的实验功能，将只记录在 Beta Devlog 中；经过验证并正式发布后，再同步到 Public Devlog。

## To-Do List

- [ ] 完成 Codex 语义排序的实现与稳定性验证。

## Beta Devlog

### 2026-08-12

- 完成研究方向配置与生成逻辑整理：
  - `config.base.yaml` 保存公开默认配置，`config.local.yaml` 保存本地客制化配置。
  - 支持直接在 YAML 的 `links` 字段中维护 arXiv 论文链接。
  - 同一个 seed group 下的多篇论文会合并为一个 interest，不会被 Codex 任意拆分成多个 ID。
  - `rewrite` 只生成当前 seed 配置对应的 interests。
  - `preserve` 保留旧 `research.yaml` 中的 interests，并增加当前样例生成的新方向。
- 当前 Beta 版与 Public 版保持一致。
- 支持基于 arXiv 的论文抓取、召回、排序和日报生成。
- 支持 PDF 解析作者机构、项目主页和代码仓库链接。
- 支持 `heuristic` 和 `codex` 两种排序器。
- 支持通过 `config.base.yaml` 与 `config.local.yaml` 管理默认配置和个人客制化配置。
- 优化论文机构信息和日报排版。

## Public Devlog

### 2026-08-12

- 当前 Public 版与 Beta 版保持一致。
- 支持基于 arXiv 的论文抓取、召回、排序和日报生成。
- 支持 PDF 解析作者机构、项目主页和代码仓库链接。
- 支持 `heuristic` 和 `codex` 两种排序器。
- 支持通过 `config.base.yaml` 与 `config.local.yaml` 管理默认配置和个人客制化配置。
- 优化论文机构信息和日报排版。
