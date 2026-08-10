# -*- coding: utf-8 -*-
"""双色球 ML 模块：纯 Python 决策树 + 随机森林，逐号码二分类预测下期开出概率。
特征只用目标期之前的历史数据，避免未来信息泄漏。"""
import random

# ---------- 决策树（CART，直方图分桶分裂） ----------
class DecisionTree:
    def __init__(self, max_depth=6, min_samples_leaf=30, max_features="sqrt", seed=0):
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.max_features = max_features
        self.seed = seed
        self.root = None
        self.F = 0

    def fit(self, X, y, w, idxs):
        self.F = len(X[0])
        self._rng = random.Random(self.seed)
        self.root = self._grow(X, y, w, list(idxs), 0)

    def _cands(self):
        k = max(1, int(self.F ** 0.5)) if self.max_features == "sqrt" else min(self.F, self.max_features)
        return self._rng.sample(range(self.F), k)

    def _grow(self, X, y, w, idxs, depth):
        pos_w = 0.0; tot_w = 0.0; pos_raw = 0
        for i in idxs:
            wi = w[i]
            tot_w += wi
            pos_w += wi if y[i] else 0.0
            pos_raw += 1 if y[i] else 0
        if (depth >= self.max_depth or len(idxs) < self.min_samples_leaf * 2
                or pos_w == 0.0 or pos_w == tot_w):
            return {"leaf": True, "prob": pos_raw / len(idxs)}
        best = None
        cur_g = self._gini(pos_w, tot_w - pos_w, tot_w)
        for f in self._cands():
            buckets = {}
            for i in idxs:
                v = X[i][f]
                if v not in buckets:
                    buckets[v] = [0.0, 0.0]
                b = buckets[v]
                if y[i]: b[0] += w[i]
                else: b[1] += w[i]
            vals = sorted(buckets.items())
            lp = ln = 0.0
            for j in range(len(vals) - 1):
                v, (p, ng) = vals[j]
                lp += p; ln += ng
                rp = pos_w - lp; rn = (tot_w - pos_w) - ln
                if lp + ln < self.min_samples_leaf or rp + rn < self.min_samples_leaf:
                    continue
                gi = ((lp + ln) / tot_w) * self._gini(lp, ln, lp + ln) \
                     + ((rp + rn) / tot_w) * self._gini(rp, rn, rp + rn)
                if best is None or gi < best[0]:
                    best = (gi, f, v)
        if best is None or best[0] >= cur_g:
            return {"leaf": True, "prob": pos_raw / len(idxs)}
        _, f, thr = best
        l_idx = [i for i in idxs if X[i][f] <= thr]
        r_idx = [i for i in idxs if X[i][f] > thr]
        if not l_idx or not r_idx:
            return {"leaf": True, "prob": pos_raw / len(idxs)}
        return {"leaf": False, "f": f, "thr": thr,
                "left": self._grow(X, y, w, l_idx, depth + 1),
                "right": self._grow(X, y, w, r_idx, depth + 1)}

    @staticmethod
    def _gini(p, q, s):
        if s <= 0: return 0.0
        return 1.0 - (p / s) ** 2 - (q / s) ** 2

    def predict_proba(self, X):
        out = []
        for x in X:
            node = self.root
            while not node["leaf"]:
                node = node["left"] if x[node["f"]] <= node["thr"] else node["right"]
            out.append(node["prob"])
        return out

# ---------- 随机森林（Bagging + 特征随机抽样） ----------
class RandomForest:
    def __init__(self, n_estimators=30, max_depth=6, min_samples_leaf=30,
                 max_features="sqrt", bootstrap_size=3000, seed=0):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.max_features = max_features
        self.bootstrap_size = bootstrap_size
        self.seed = seed
        self.trees = []

    def fit(self, X, y, w):
        n = len(X)
        self.trees = []
        for t in range(self.n_estimators):
            rng = random.Random(self.seed + t)
            idxs = [rng.randrange(n) for _ in range(self.bootstrap_size)]
            tree = DecisionTree(self.max_depth, self.min_samples_leaf,
                                self.max_features, seed=self.seed + t * 7 + 1)
            tree.fit(X, y, w, idxs)
            self.trees.append(tree)

    def predict_proba(self, X):
        m = len(X)
        sums = [0.0] * m
        for tree in self.trees:
            p = tree.predict_proba(X)
            for i in range(m):
                sums[i] += p[i]
        return [s / len(self.trees) for s in sums]

# ---------- 特征工程（只用 t 期及之前的信息） ----------
def _cnt(seq, n, t, k, is_blue):
    s = 0
    lo = max(0, t - k + 1)
    for j in range(lo, t + 1):
        if (n in seq[j]) if not is_blue else (seq[j] == n):
            s += 1
    return s

def _om(seq, n, t, is_blue):
    """截至 t 期的当前遗漏。"""
    for j in range(t, -1, -1):
        if (n in seq[j]) if not is_blue else (seq[j] == n):
            return t - j
    return t + 1

def _avg_max_om(seq, n, t, is_blue):
    gaps, last = [], None
    for j in range(t + 1):
        ok = (n in seq[j]) if not is_blue else (seq[j] == n)
        if ok:
            if last is not None: gaps.append(j - last - 1)
            last = j
    if not gaps: return 0.0, 0
    return sum(gaps) / len(gaps), max(gaps)

def _b(v, cap, n_bins=16):
    return min(int(v / cap * n_bins), n_bins - 1) if cap else 0

def build_features(rows, n, t, is_blue):
    """返回桶化特征列表（值域 0..15），预测 t+1 期。"""
    if is_blue:
        seq = [r["蓝球"] for r in rows[:t + 1]]
        f = [n - 1]
        f.append(min(_cnt(seq, n, t, 1, True), 1))
        f.append(min(_cnt(seq, n, t, 3, True), 3))
        f.append(min(_cnt(seq, n, t, 5, True), 5))
        f.append(min(_cnt(seq, n, t, 10, True), 6))
        f.append(min(_cnt(seq, n, t, 20, True), 8))
        f.append(min(_cnt(seq, n, t, 50, True), 10))
        f.append(_b(_om(seq, n, t, True), 64))
        avg, mx = _avg_max_om(seq, n, t, True)
        f.append(_b(avg, 24))
        f.append(_b(mx, 96))
        f.append(_b(seq[t], 16))
        return f
    seq = [r["红球"] for r in rows[:t + 1]]
    f = [_b(n - 1, 33)]
    f.append(0 if n <= 11 else (1 if n <= 22 else 2))
    f.append(min(_cnt(seq, n, t, 1, False), 1))
    f.append(min(_cnt(seq, n, t, 3, False), 3))
    f.append(min(_cnt(seq, n, t, 5, False), 5))
    f.append(min(_cnt(seq, n, t, 10, False), 6))
    f.append(min(_cnt(seq, n, t, 20, False), 8))
    f.append(min(_cnt(seq, n, t, 50, False), 10))
    f.append(_b(_om(seq, n, t, False), 64))
    avg, mx = _avg_max_om(seq, n, t, False)
    f.append(_b(avg, 24))
    f.append(_b(mx, 96))
    cur = rows[t]["红球"]
    a = sum(1 <= x <= 11 for x in cur)
    b = sum(12 <= x <= 22 for x in cur)
    c = sum(23 <= x <= 33 for x in cur)
    f.extend([a, b, c])
    return f

# ---------- 数据集构建 ----------
def build_dataset(rows, is_blue, pool=1000):
    n_last = len(rows)
    t_start = max(60, n_last - pool)
    X, y = [], []
    nums = range(1, 17) if is_blue else range(1, 34)
    for t in range(t_start, n_last - 1):
        for n in nums:
            X.append(build_features(rows, n, t, is_blue))
            if is_blue:
                y.append(1 if rows[t + 1]["蓝球"] == n else 0)
            else:
                y.append(1 if n in rows[t + 1]["红球"] else 0)
    return X, y

def balanced_weights(y):
    pos = sum(y); neg = len(y) - pos
    total = len(y)
    return [total / (2 * pos) if yi else total / (2 * neg) for yi in y]

# ---------- 训练与预测 ----------
def train(rows, n_estimators=60, bootstrap=3000):
    t0 = __import__("time").time()
    Xr, yr = build_dataset(rows, False)
    Xb, yb = build_dataset(rows, True)
    wr, wb = balanced_weights(yr), balanced_weights(yb)
    dt_red = DecisionTree(seed=11); dt_red.fit(Xr, yr, wr, range(len(Xr)))
    dt_blue = DecisionTree(seed=12); dt_blue.fit(Xb, yb, wb, range(len(Xb)))
    rf_red = RandomForest(n_estimators=n_estimators, bootstrap_size=bootstrap, seed=21)
    rf_red.fit(Xr, yr, wr)
    rf_blue = RandomForest(n_estimators=n_estimators, bootstrap_size=bootstrap, seed=22)
    rf_blue.fit(Xb, yb, wb)
    dt = __import__("time").time() - t0
    return {"dt_red": dt_red, "dt_blue": dt_blue, "rf_red": rf_red, "rf_blue": rf_blue,
            "sample": {"red": len(yr), "blue": len(yb)}, "train_sec": round(dt, 1)}

def _zn(n):
    return 0 if n <= 11 else (1 if n <= 22 else 2)

def constrain_red(probs):
    """分区均衡选择：每区至少1个、最多3个，其余按概率贪心补齐。"""
    nums = list(range(1, 34))
    order = sorted(zip(nums, probs), key=lambda z: -z[1])
    cnt = [0, 0, 0]
    sel = []
    # 第一轮：每区概率最高者各1个
    for z in range(3):
        for n, p in order:
            if _zn(n) == z and cnt[z] == 0:
                sel.append((n, p)); cnt[z] += 1
                break
    # 第二轮：全局按概率补满6个，每区上限3
    for n, p in order:
        if len(sel) >= 6:
            break
        z = _zn(n)
        if cnt[z] >= 3 or any(n == m for m, _ in sel):
            continue
        sel.append((n, p)); cnt[z] += 1
    sel.sort(key=lambda z: -z[1])
    return [{"n": n, "p": round(p, 4)} for n, p in sel]

def predict(rows, models, t_target):
    """预测第 t_target+1 期（即目标期）。返回各模型 Top 列表。"""
    def top(probs, nums, k):
        order = sorted(zip(nums, probs), key=lambda z: -z[1])
        return [{"n": n, "p": round(p, 4)} for n, p in order[:k]]

    Xr = [build_features(rows, n, t_target, False) for n in range(1, 34)]
    Xb = [build_features(rows, n, t_target, True) for n in range(1, 17)]
    dtr = models["dt_red"].predict_proba(Xr)
    dbb = models["dt_blue"].predict_proba(Xb)
    rfr = models["rf_red"].predict_proba(Xr)
    rfb = models["rf_blue"].predict_proba(Xb)
    fused_r = [a * 0.4 + b * 0.6 for a, b in zip(dtr, rfr)]
    fused_b = [a * 0.4 + b * 0.6 for a, b in zip(dbb, rfb)]
    dt_red = top(dtr, range(1, 34), 6)
    dt_blue = top(dbb, range(1, 17), 3)
    rf_red = top(rfr, range(1, 34), 6)
    rf_blue = top(rfb, range(1, 17), 3)
    fu_red = constrain_red(fused_r)
    fu_blue = top(fused_b, range(1, 17), 3)
    return {"dt": {"red": dt_red, "blue": dt_blue},
            "rf": {"red": rf_red, "blue": rf_blue},
            "fusion": {"red": fu_red, "blue": fu_blue},
            "sample": models["sample"], "train_sec": models["train_sec"]}

if __name__ == "__main__":
    import sys, csv
    def load(p):
        with open(p, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["红球"] = [int(r["红%d" % i]) for i in range(1, 7)]
            r["蓝球"] = int(r["蓝球"])
        return rows
    rows = load(r"C:\Users\flycat\Documents\学习上手\双色球分析\双色球开奖数据_全量历史.csv")
    print("训练中…")
    models = train(rows)
    print("训练完成，耗时 %.1f 秒，样本: %s" % (models["train_sec"], models["sample"]))
    res = predict(rows, models, len(rows) - 1)
    print("决策树红球Top6:", [(d["n"], d["p"]) for d in res["dt"]["red"]])
    print("随机森林红球Top6:", [(d["n"], d["p"]) for d in res["rf"]["red"]])
    print("融合红球Top6:", [(d["n"], d["p"]) for d in res["fusion"]["red"]])
    print("决策树蓝球Top3:", [(d["n"], d["p"]) for d in res["dt"]["blue"]])
    print("随机森林蓝球Top3:", [(d["n"], d["p"]) for d in res["rf"]["blue"]])
    print("融合蓝球Top3:", [(d["n"], d["p"]) for d in res["fusion"]["blue"]])
