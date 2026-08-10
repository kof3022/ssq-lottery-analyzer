# -*- coding: utf-8 -*-
"""双色球分区 + 频率遗漏分析 + 马尔可夫链分析，生成近10期逐期分析报告。"""
import csv, os, json, itertools
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
FULL_CSV = os.path.join(BASE, "双色球开奖数据_全量历史.csv")
ZONE_CSV = os.path.join(BASE, "双色球分区数据_最近100期.csv")
FREQ_CSV = os.path.join(BASE, "双色球频率遗漏汇总.csv")
MC_CSV = os.path.join(BASE, "双色球马尔可夫转移矩阵.csv")
REPORT_MD = os.path.join(BASE, "双色球分析报告_近10期.md")

ZONES = [(1, 11), (12, 22), (23, 33)]
ZONE_NAMES = ["一区(1-11)", "二区(12-22)", "三区(23-33)"]

def load_rows(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["期号"] = r["期号"].strip()
        r["红球"] = [int(r["红%d" % i]) for i in range(1, 7)]
        r["蓝球"] = int(r["蓝球"])
    return rows

def zone_counts(reds):
    return tuple(sum(lo <= x <= hi for x in reds) for lo, hi in ZONES)

def zone_numbers(reds):
    return [tuple(sorted(x for x in reds if lo <= x <= hi)) for lo, hi in ZONES]

def omission_stats(sample, nums_range, kind):
    """号码在样本内的平均遗漏、最大遗漏、当前遗漏(样本末+1时刻)。"""
    stats = {}
    for n in nums_range:
        last_idx = None
        gaps = []
        for i, r in enumerate(sample):
            present = (n in r["红球"]) if kind == "red" else (r["蓝球"] == n)
            if present:
                if last_idx is not None:
                    gaps.append(i - last_idx - 1)
                last_idx = i
        avg = sum(gaps) / len(gaps) if gaps else float("nan")
        mx = max(gaps) if gaps else 0
        cur = (len(sample) - 1 - last_idx) if last_idx is not None else len(sample)
        stats[n] = {"平均遗漏": avg, "最大遗漏": mx, "当前遗漏": cur, "出现次数": len(gaps) + (1 if last_idx is not None else 0)}
    return stats

def state_omission(sample, key_fn, states):
    """状态(如各区出号个数)在样本内的平均遗漏/最大遗漏/当前遗漏。"""
    stats = {}
    for st in states:
        last_idx = None
        gaps = []
        for i, r in enumerate(sample):
            if key_fn(r) == st:
                if last_idx is not None:
                    gaps.append(i - last_idx - 1)
                last_idx = i
        avg = sum(gaps) / len(gaps) if gaps else float("nan")
        mx = max(gaps) if gaps else 0
        cur = (len(sample) - 1 - last_idx) if last_idx is not None else len(sample)
        stats[st] = {"平均遗漏": avg, "最大遗漏": mx, "当前遗漏": cur, "出现次数": len(gaps) + (1 if last_idx is not None else 0)}
    return stats

def markov_matrix(sample, states, key_fn):
    """一阶马尔可夫转移矩阵，拉普拉斯平滑 alpha=1。返回 (矩阵, 计数)。"""
    n = len(states)
    idx = {s: i for i, s in enumerate(states)}
    count = [[0] * n for _ in range(n)]
    for i in range(len(sample) - 1):
        a, b = key_fn(sample[i]), key_fn(sample[i + 1])
        count[idx[a]][idx[b]] += 1
    prob = [[(count[i][j] + 1) / (sum(count[i]) + n) for j in range(n)] for i in range(n)]
    return prob, count, idx

def prob_from_to(prob, idx, s_from, s_to):
    return prob[idx[s_from]][idx[s_to]]

def fmt_num(x):
    return "%.1f%%" % (x * 100) if isinstance(x, float) else str(x)

def fmt_om(s):
    return "-" if s["出现次数"] <= 1 else "%.1f" % s["平均遗漏"]

def fmt_max(s):
    return "-" if s["出现次数"] <= 1 else str(s["最大遗漏"])

def red_freq(sample):
    c = Counter()
    for r in sample:
        c.update(r["红球"])
    return {n: c.get(n, 0) / len(sample) for n in range(1, 34)}

def blue_freq(sample):
    c = Counter(r["蓝球"] for r in sample)
    return {n: c.get(n, 0) / len(sample) for n in range(1, 17)}

def main():
    rows = load_rows(FULL_CSV)
    for r in rows:
        r["分区"] = zone_counts(r["红球"])
        r["区号"] = zone_numbers(r["红球"])
    last100 = rows[-100:]
    recent10 = rows[-10:]

    # ---- 分区数据CSV（最近100期）----
    with open(ZONE_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["期号", "开奖日期", "红球", "蓝球", "一区个数", "二区个数", "三区个数"])
        for r in last100:
            w.writerow([r["期号"], r["开奖日期"], " ".join("%02d" % x for x in r["红球"]),
                        "%02d" % r["蓝球"], r["分区"][0], r["分区"][1], r["分区"][2]])

    combos = [(a, b, c) for a in range(7) for b in range(7) for c in range(7) if a + b + c == 6]
    blue_states = list(range(1, 17))

    # ---- 近10期逐期滚动分析 ----
    per_issue = []
    for t in recent10:
        idx = rows.index(t)
        sample = rows[:idx]  # 截至上一期的全部历史
        w100 = rows[max(0, idx - 100):idx]  # 截至上一期的最近100期

        # 频率
        combo_freq = Counter(r["分区"] for r in sample)
        combo_freq100 = Counter(r["分区"] for r in w100)
        zone_freq = [Counter(r["分区"][i] for r in sample) for i in range(3)]
        blue_f = Counter(r["蓝球"] for r in sample)

        # 遗漏
        red_om = omission_stats(sample, range(1, 34), "red")
        blue_om = omission_stats(sample, range(1, 17), "blue")
        combo_om = state_omission(sample, lambda r: r["分区"], combos)
        zone_om = [state_omission(sample, lambda r: r["分区"][i], range(7)) for i in range(3)]

        # 马尔可夫
        mc_combo = markov_matrix(sample, combos, lambda r: r["分区"])
        mc_blue = markov_matrix(sample, blue_states, lambda r: r["蓝球"])
        mc_zone = [markov_matrix(sample, list(range(7)), lambda r, i=i: r["分区"][i]) for i in range(3)]

        prev = sample[-1]
        p_combo = prob_from_to(mc_combo[0], mc_combo[2], prev["分区"], t["分区"])
        p_blue = prob_from_to(mc_blue[0], mc_blue[2], prev["蓝球"], t["蓝球"])
        p_zone = [prob_from_to(mc_zone[i][0], mc_zone[i][2], prev["分区"][i], t["分区"][i]) for i in range(3)]

        per_issue.append({
            "期": t, "样本数": len(sample),
            "组合频率": combo_freq[t["分区"]] / len(sample),
            "组合频率100": combo_freq100[t["分区"]] / len(w100) if w100 else None,
            "组合出现次数": combo_freq[t["分区"]],
            "各区频率": [zone_freq[i][t["分区"][i]] / len(sample) for i in range(3)],
            "蓝球频率": blue_f[t["蓝球"]] / len(sample),
            "组合遗漏": combo_om[t["分区"]],
            "各区遗漏": [zone_om[i][t["分区"][i]] for i in range(3)],
            "红球遗漏": {n: red_om[n] for n in t["红球"]},
            "蓝球遗漏": blue_om[t["蓝球"]],
            "马尔可夫组合": p_combo,
            "马尔可夫蓝球": p_blue,
            "马尔可夫各区": p_zone,
        })

    # ---- 静态汇总（最近100期 与 全量）----
    def summarize(sample, label):
        return {
            "label": label,
            "红球频率": red_freq(sample),
            "蓝球频率": blue_freq(sample),
            "红球遗漏": omission_stats(sample, range(1, 34), "red"),
            "蓝球遗漏": omission_stats(sample, range(1, 17), "blue"),
            "组合频率": Counter(r["分区"] for r in sample),
            "各区分布": [Counter(r["分区"][i] for r in sample) for i in range(3)],
        }
    sum100 = summarize(rows[-100:], "最近100期")
    sumall = summarize(rows, "全量2013-2026")

    # ---- 频率遗漏汇总CSV ----
    with open(FREQ_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["类别", "号码/状态", "100期频率", "100期当前遗漏", "100期平均遗漏", "100期最大遗漏",
                    "全量频率", "全量当前遗漏", "全量平均遗漏", "全量最大遗漏"])
        for n in range(1, 34):
            s1, s2 = sum100["红球遗漏"][n], sumall["红球遗漏"][n]
            w.writerow(["红球%02d" % n, n, "%.1f%%" % (sum100["红球频率"][n]*100), s1["当前遗漏"],
                        fmt_om(s1), fmt_max(s1),
                        "%.1f%%" % (sumall["红球频率"][n]*100), s2["当前遗漏"],
                        fmt_om(s2), fmt_max(s2)])
        for n in range(1, 17):
            s1, s2 = sum100["蓝球遗漏"][n], sumall["蓝球遗漏"][n]
            w.writerow(["蓝球%02d" % n, n, "%.1f%%" % (sum100["蓝球频率"][n]*100), s1["当前遗漏"],
                        fmt_om(s1), fmt_max(s1),
                        "%.1f%%" % (sumall["蓝球频率"][n]*100), s2["当前遗漏"],
                        fmt_om(s2), fmt_max(s2)])

    # ---- 马尔可夫矩阵CSV ----
    mc_full_combo = markov_matrix(rows, combos, lambda r: r["分区"])
    mc_full_blue = markov_matrix(rows, blue_states, lambda r: r["蓝球"])
    mc_full_zone = [markov_matrix(rows, list(range(7)), lambda r, i=i: r["分区"][i]) for i in range(3)]
    with open(MC_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        for name, mc in [("红球组合状态(一区,二区,三区)", mc_full_combo),
                         ("蓝球号码", mc_full_blue)]:
            prob, count, idx = mc
            states = sorted(idx, key=lambda s: idx[s])
            w.writerow([name])
            w.writerow(["从\\到"] + ["%s" % (s if isinstance(s, int) else "-".join(map(str, s))) for s in states])
            for s in states:
                i = idx[s]
                w.writerow(["%s" % (s if isinstance(s, int) else "-".join(map(str, s)))] + ["%.3f" % prob[i][j] for j in range(len(states))])
            w.writerow([])
        for i, name in enumerate(["一区(1-11)", "二区(12-22)", "三区(23-33)"]):
            prob, count, idx = mc_full_zone[i]
            states = range(7)
            w.writerow(["%s 出号个数转移" % name])
            w.writerow(["从\\到"] + list(states))
            for s in states:
                w.writerow([s] + ["%.3f" % prob[idx[s]][j] for j in states])
            w.writerow([])

    # ---- 下一期概率参考 ----
    last = rows[-1]
    combos_sorted = sorted(combos, key=lambda s: -mc_full_combo[0][mc_full_combo[2][last["分区"]]][mc_full_combo[2][s]])
    top_combos = combos_sorted[:5]
    blues_sorted = sorted(blue_states, key=lambda s: -mc_full_blue[0][mc_full_blue[2][last["蓝球"]]][mc_full_blue[2][s]])
    top_blues = blues_sorted[:5]

    # ---- 生成Markdown报告 ----
    L = []
    L.append("# 双色球近10期分析报告")
    L.append("")
    L.append("> 数据来源：中国福彩官网双色球开奖数据（截至 %s，最新一期 %s）。" % (rows[-1]["开奖日期"], rows[-1]["期号"]))
    L.append("> 样本：全量历史 %d 期（2013001–%s）。滚动分析中，每一期只用**该期之前**的历史数据计算，避免「未来数据」污染。频率/遗漏另附最近100期静态汇总。" % (len(rows), rows[-1]["期号"]))
    L.append("> **重要说明**：彩票开奖为独立随机事件，以下频率、遗漏与马尔可夫概率仅为历史结构观察，不构成任何投注建议。")
    L.append("")
    L.append("---")
    L.append("")

    # 逐期
    L.append("## 一、近10期逐期分析")
    L.append("")
    for i, p in enumerate(per_issue):
        t = p["期"]
        L.append("### 第 %s 期（%s）" % (t["期号"], t["开奖日期"]))
        L.append("")
        L.append("| 项目 | 内容 |")
        L.append("|---|---|")
        L.append("| 红球 | %s |" % " ".join("%02d" % x for x in t["红球"]))
        L.append("| 蓝球 | %02d |" % t["蓝球"])
        L.append("| 分区 | 一区 **%d** 个、二区 **%d** 个、三区 **%d** 个 |" % t["分区"])
        L.append("| 样本量 | %d 期（截至上一期） |" % p["样本数"])
        L.append("")
        L.append("**频率分析**：")
        L.append("")
        L.append("- 分区组合 `(%d,%d,%d)` 历史出现 %d 次，占比 **%.1f%%**；近100期口径占比 **%.1f%%**。" % (
            t["分区"][0], t["分区"][1], t["分区"][2], p["组合出现次数"], p["组合频率"] * 100,
            (p["组合频率100"] or 0) * 100))
        L.append("- 各区出号个数在本期前历史占比：一区%d个 **%.1f%%**、二区%d个 **%.1f%%**、三区%d个 **%.1f%%**。" % (
            t["分区"][0], p["各区频率"][0] * 100, t["分区"][1], p["各区频率"][1] * 100,
            t["分区"][2], p["各区频率"][2] * 100))
        L.append("- 蓝球 %02d 历史出现频率 **%.1f%%**。" % (t["蓝球"], p["蓝球频率"] * 100))
        L.append("")
        L.append("**遗漏分析**（开出前状态）：")
        L.append("")
        L.append("- 分区组合 `(%d,%d,%d)` 开出前已遗漏 **%d** 期（历史平均 %.1f 期、最大 %d 期）。" % (
            t["分区"][0], t["分区"][1], t["分区"][2], p["组合遗漏"]["当前遗漏"],
            p["组合遗漏"]["平均遗漏"], p["组合遗漏"]["最大遗漏"]))
        L.append("- 各区个数状态遗漏：一区%d个 **%d** 期、二区%d个 **%d** 期、三区%d个 **%d** 期（历史平均分别为 %.1f / %.1f / %.1f）。" % (
            t["分区"][0], p["各区遗漏"][0]["当前遗漏"], t["分区"][1], p["各区遗漏"][1]["当前遗漏"],
            t["分区"][2], p["各区遗漏"][2]["当前遗漏"],
            p["各区遗漏"][0]["平均遗漏"], p["各区遗漏"][1]["平均遗漏"], p["各区遗漏"][2]["平均遗漏"]))
        red_parts = []
        for n in t["红球"]:
            s = p["红球遗漏"][n]
            tag = "补漏开出" if s["当前遗漏"] > s["平均遗漏"] else ("热号续热" if s["当前遗漏"] == 0 else "常态")
            red_parts.append("红%02d 漏%d期(均%.1f)→%s" % (n, s["当前遗漏"], s["平均遗漏"], tag))
        L.append("- 本期红球开出前遗漏情况：" + "；".join(red_parts) + "。")
        bs = p["蓝球遗漏"]
        btag = "补漏开出" if bs["当前遗漏"] > bs["平均遗漏"] else ("热号续热" if bs["当前遗漏"] == 0 else "常态")
        L.append("- 蓝球 %02d 开出前遗漏 **%d** 期（历史平均 %.1f 期、最大 %d 期）→ %s。" % (
            t["蓝球"], bs["当前遗漏"], bs["平均遗漏"], bs["最大遗漏"], btag))
        L.append("")
        L.append("**马尔可夫链分析**（一阶转移概率，拉普拉斯平滑）：")
        L.append("")
        L.append("- 分区组合状态 `%s → %s` 的历史转移概率 **%.1f%%**。" % (
            "-".join(map(str, prev_comb(t, per_issue, p, rows))), "-".join(map(str, t["分区"])),
            p["马尔可夫组合"] * 100))
        L.append("- 各区出号个数转移概率：一区 **%.1f%%**、二区 **%.1f%%**、三区 **%.1f%%**。" % (
            p["马尔可夫各区"][0] * 100, p["马尔可夫各区"][1] * 100, p["马尔可夫各区"][2] * 100))
        L.append("- 蓝球 %02d → %02d 的转移概率 **%.1f%%**。" % (prev_blue(p, per_issue, rows), t["蓝球"], p["马尔可夫蓝球"] * 100))
        L.append("")
        L.append("---")
        L.append("")

    L.append("## 二、近10期汇总")
    L.append("")
    L.append("| 期号 | 红球 | 蓝球 | 分区(一二三) | 组合频率 | 组合开出前遗漏 | 组合转移概率 |")
    L.append("|---|---|---|---|---|---|---|")
    for p in per_issue:
        t = p["期"]
        L.append("| %s | %s | %02d | %d/%d/%d | %.1f%% | %d期 | %.1f%% |" % (
            t["期号"], " ".join("%02d" % x for x in t["红球"]), t["蓝球"],
            t["分区"][0], t["分区"][1], t["分区"][2],
            p["组合频率"] * 100, p["组合遗漏"]["当前遗漏"], p["马尔可夫组合"] * 100))
    L.append("")
    L.append("近10期各区出号个数均值：一区 **%.2f**、二区 **%.2f**、三区 **%.2f**；最近100期均值：%.2f / %.2f / %.2f；全量均值：%.2f / %.2f / %.2f。" % (
        sum(p["期"]["分区"][0] for p in per_issue) / 10,
        sum(p["期"]["分区"][1] for p in per_issue) / 10,
        sum(p["期"]["分区"][2] for p in per_issue) / 10,
        sum(r["分区"][0] for r in rows[-100:]) / 100,
        sum(r["分区"][1] for r in rows[-100:]) / 100,
        sum(r["分区"][2] for r in rows[-100:]) / 100,
        sum(r["分区"][0] for r in rows) / len(rows),
        sum(r["分区"][1] for r in rows) / len(rows),
        sum(r["分区"][2] for r in rows) / len(rows)))
    L.append("")

    L.append("## 三、频率与遗漏汇总（最近100期口径）")
    L.append("")
    L.append("### 红球各区出号个数分布（最近100期）")
    L.append("")
    L.append("| 区 | 0个 | 1个 | 2个 | 3个 | 4个 | 5个 | 6个 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for i, name in enumerate(ZONE_NAMES):
        c = sum100["各区分布"][i]
        L.append("| %s | %s |" % (name, " | ".join("%d期(%.0f%%)" % (c.get(k, 0), c.get(k, 0)) for k in range(7))))
    L.append("")
    L.append("### 分区组合频率 Top10（最近100期）")
    L.append("")
    L.append("| 组合(一,二,三) | 出现期数 | 占比 |")
    L.append("|---|---|---|")
    for (combo, cnt) in sum100["组合频率"].most_common(10):
        L.append("| (%d,%d,%d) | %d | %.1f%% |" % (combo[0], combo[1], combo[2], cnt, cnt / 100 * 100))
    L.append("")
    L.append("### 红球号码热冷（最近100期）")
    L.append("")
    L.append("| 号码 | 频率 | 当前遗漏 | 平均遗漏 | 最大遗漏 |")
    L.append("|---|---|---|---|---|")
    for n, f in sorted(sum100["红球频率"].items(), key=lambda kv: -kv[1]):
        s = sum100["红球遗漏"][n]
        L.append("| %02d | %.1f%% | %d | %s | %s |" % (n, f * 100, s["当前遗漏"], fmt_om(s), fmt_max(s)))
    L.append("")
    L.append("### 蓝球号码热冷（最近100期）")
    L.append("")
    L.append("| 号码 | 频率 | 当前遗漏 | 平均遗漏 | 最大遗漏 |")
    L.append("|---|---|---|---|---|")
    for n, f in sorted(sum100["蓝球频率"].items(), key=lambda kv: -kv[1]):
        s = sum100["蓝球遗漏"][n]
        L.append("| %02d | %.1f%% | %d | %s | %s |" % (n, f * 100, s["当前遗漏"], fmt_om(s), fmt_max(s)))
    L.append("")

    L.append("## 四、下一期概率参考（基于全量历史的马尔可夫链）")
    L.append("")
    L.append("> 仅供参考，非预测结论。")
    L.append("")
    L.append("从最新一期 %s（分区 %d/%d/%d，蓝球 %02d）出发：" % (
        last["期号"], last["分区"][0], last["分区"][1], last["分区"][2], last["蓝球"]))
    L.append("- 分区组合状态转移概率最高前5：%s" % "、".join(
        "(%d,%d,%d) %.1f%%" % (s[0], s[1], s[2],
            mc_full_combo[0][mc_full_combo[2][last["分区"]]][mc_full_combo[2][s]] * 100) for s in top_combos))
    L.append("- 蓝球号码转移概率最高前5：%s" % "、".join(
        "%02d %.1f%%" % (s, mc_full_blue[0][mc_full_blue[2][last["蓝球"]]][mc_full_blue[2][s]] * 100) for s in top_blues))
    L.append("")
    L.append("## 五、方法说明")
    L.append("")
    L.append("- **分区**：红球一区 1–11、二区 12–22、三区 23–33；蓝球 1–16。")
    L.append("- **频率分析**：统计各分区出号个数与号码出现占比，识别热/冷。")
    L.append("- **遗漏分析**：统计号码与分区状态连续未出现的期数（当前遗漏），并与平均遗漏、最大遗漏对比。")
    L.append("- **马尔可夫链**：将每期状态（分区组合或蓝球号码）视为一阶马尔可夫过程，用历史转移对估计转移概率矩阵，并做拉普拉斯平滑（α=1）以缓解稀疏问题。")
    L.append("")

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print("已生成：")
    print("  %s" % ZONE_CSV)
    print("  %s" % FREQ_CSV)
    print("  %s" % MC_CSV)
    print("  %s" % REPORT_MD)
    print("近10期：%s ~ %s" % (recent10[0]["期号"], recent10[-1]["期号"]))

def prev_comb(t, per_issue, p, rows):
    idx = rows.index(t)
    return rows[idx - 1]["分区"]

def prev_blue(p, per_issue, rows):
    idx = rows.index(p["期"])
    return rows[idx - 1]["蓝球"]

if __name__ == "__main__":
    main()
