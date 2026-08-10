# GitHub 仓库简介

## 中文

**双色球走势分析工具**：基于中国福彩官网公开开奖数据的本地分析工具。提供极简网页界面，支持一键刷新最新开奖、指定期分析，综合运用分区频率、遗漏分析、马尔可夫链以及自实现的决策树与随机森林模型，给出下一期推荐。纯 Python 标准库实现，零第三方依赖，双击即用。

## English

**SSQ Lottery Trend Analyzer**: A local web tool for analyzing China Welfare Lottery SSQ (Double Color Ball) trends. It uses official public draw data, offers a minimal web UI with one-click data refresh and issue-based analysis, and combines zone frequency / omission analysis, Markov chains, plus self-implemented decision tree & random forest models to suggest next-draw numbers. Pure Python standard library, zero third-party dependencies, run with one double-click.

---

# Release Notes

## v1.0.0（2026-08-10）

### 亮点 / Highlights

- 极简本地网页界面，双击 `启动双色球工具.bat` 即可使用，自动打开浏览器
- 一键刷新最新开奖数据（福彩官网公开接口，无鉴权、无 API Key）
- 指定期分析：支持任意已开奖期号或下一期，自动使用该期之前 **528 期**历史数据
- 双轮分析：第一轮前 528 期 + 第二轮最近 16 期，输出"前528期 + 近16期加权"综合推荐一注
- 多方法推荐：
  - 分区（红球一区 1-11 / 二区 12-22 / 三区 23-33，蓝球 1-16）频率与遗漏分析
  - 马尔可夫链转移概率（`analysis.py` 离线报告）
  - 决策树 + 随机森林（`ml_model.py`，纯 Python 自实现，逐号码输出下期开出概率）
- 过去期验证：分析历史期号时显示实际开奖号码供对比
- 端口冲突自动回退，多实例安全

### 安装与使用 / Install & Usage

- 环境要求：Windows + Python 3.8+（仅标准库，无需 pip 安装）
- 方式一：双击 `启动双色球工具.bat`
- 方式二：命令行运行 `python server.py`，浏览器访问 `http://127.0.0.1:8765`

### 数据与免责声明 / Data & Disclaimer

- 数据来源：中国福彩官网公开开奖数据（`cwl.gov.cn`）
- 开奖结果独立随机，本工具仅做历史数据统计展示，**不构成任何投注建议，请理性购彩**
- 本项目按 MIT License 开源

### 更新日志 / Changelog

- **v1.0.0**：初始版本。数据下载、双轮分区分析、马尔可夫报告、决策树/随机森林推荐、极简页面、文档与 License 就绪。
