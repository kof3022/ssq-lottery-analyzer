# -*- coding: utf-8 -*-
"""双色球走势分析工具 - 本地服务：数据刷新 + 指定期分析 API + 静态页面。"""
import csv, json, os, re, socket, sys, threading, urllib.request, webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import ml_model

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "双色球开奖数据_全量历史.csv")
HTML_PATH = os.path.join(BASE, "index.html")
PORT = 8765
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/",
}
STATE = {"rows": [], "refresh_time": None}
ML_LOCK = threading.Lock()
ML_MODELS = {"models": None}

def load_rows():
    rows = []
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append({
                "期号": r["期号"].strip(),
                "开奖日期": r["开奖日期"],
                "星期": r["星期"],
                "红球": [int(r["红%d" % i]) for i in range(1, 7)],
                "蓝球": int(r["蓝球"]),
            })
    rows.sort(key=lambda x: x["期号"])
    return rows

def save_csv(rows):
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["期号", "开奖日期", "星期", "红1", "红2", "红3", "红4", "红5", "红6", "蓝球"])
        for r in rows:
            w.writerow([r["期号"], r["开奖日期"], r["星期"]] + r["红球"] + [r["蓝球"]])

def fetch_remote():
    url = ("https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/"
           "findDrawNotice?name=ssq&issueCount=3000")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("state") != 0 or not data.get("result"):
        raise RuntimeError("官网接口返回异常")
    rows = []
    for item in data["result"]:
        reds = [int(x) for x in re.findall(r"\d+", item["red"])]
        rows.append({
            "期号": str(item["code"]),
            "开奖日期": str(item["date"]).split("(")[0].strip(),
            "星期": str(item.get("week", "")).strip(),
            "红球": reds,
            "蓝球": int(item["blue"]),
        })
    rows.sort(key=lambda x: x["期号"])
    return rows

def refresh():
    rows = fetch_remote()
    save_csv(rows)
    STATE["rows"] = rows
    STATE["refresh_time"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
    ML_MODELS["models"] = None

# ---------- 分析逻辑 ----------
ZONES = [("一区(1-11)", 1, 11), ("二区(12-22)", 12, 22), ("三区(23-33)", 23, 33)]

def current_om(rows, n, anchor_idx, is_blue):
    """目标期开奖前（截至 anchor_idx-1）号码 n 的当前遗漏（基于全量历史）。"""
    for i in range(anchor_idx - 1, -1, -1):
        present = (n in rows[i]["红球"]) if not is_blue else (rows[i]["蓝球"] == n)
        if present:
            return anchor_idx - 1 - i
    return None

def avg_om_presence(presence):
    """按期序列(每期是否出现)计算平均遗漏期数。"""
    gaps, last = [], None
    for i, ok in enumerate(presence):
        if ok:
            if last is not None:
                gaps.append(i - last - 1)
            last = i
    return (sum(gaps) / len(gaps)) if gaps else None

def analyze_window(rows, window, anchor):
    """对给定窗口计算分区频率/遗漏/推荐。"""
    N = len(window)
    zones = {}
    for name, lo, hi in ZONES:
        cnt = Counter(x for r in window for x in r["红球"] if lo <= x <= hi)
        total = sum(cnt.values())
        items = []
        for n in range(lo, hi + 1):
            om = current_om(rows, n, anchor, False)
            aom = avg_om_presence([n in r["红球"] for r in window])
            items.append({"n": n, "count": cnt[n], "freq": round(cnt[n] / total * 100, 1),
                          "cur_om": om, "avg_om": aom})
        items.sort(key=lambda t: (-t["count"], t["cur_om"]))
        zones[name] = {"total": total, "avg_per": round(total / N, 2), "items": items,
                       "top": [t["n"] for t in items[:2]],
                       "backup": [t["n"] for t in items[2:4]],
                       "bule": [t["n"] for t in sorted(
                           [x for x in items if x["cur_om"] is not None and
                            (x["avg_om"] is None or x["cur_om"] >= (x["avg_om"] + 3))],
                           key=lambda t: -t["cur_om"])[:3]]}
    bc = Counter(r["蓝球"] for r in window)
    items = []
    for n in range(1, 17):
        om = current_om(rows, n, anchor, True)
        aom = avg_om_presence([r["蓝球"] == n for r in window])
        items.append({"n": n, "count": bc[n], "freq": round(bc[n] / N * 100, 1),
                      "cur_om": om, "avg_om": aom})
    items.sort(key=lambda t: (-t["count"], t["cur_om"]))
    def bscore(t):
        s = t["freq"]
        if t["avg_om"] is not None and t["cur_om"] is not None and t["cur_om"] >= t["avg_om"]:
            s += 3
        if t["cur_om"] == 0:
            s += 1
        return s
    bsorted = sorted(items, key=bscore, reverse=True)
    zones["蓝球(1-16)"] = {"total": sum(bc.values()), "avg_per": round(N / 16, 2),
                           "items": items,
                           "top": [t["n"] for t in bsorted[:1]],
                           "backup": [t["n"] for t in bsorted[1:3]],
                           "bule": [t["n"] for t in sorted(
                               [x for x in items if x["cur_om"] is not None and
                                (x["avg_om"] is None or x["cur_om"] >= (x["avg_om"] + 3))],
                               key=lambda t: -t["cur_om"])[:5]]}
    rec_red = []
    for name, lo, hi in ZONES:
        rec_red.extend(zones[name]["top"])
    rec_blue = zones["蓝球(1-16)"]["top"][0]
    return {"zones": zones, "recommend": {
        "red": rec_red, "blue": rec_blue,
        "red_by_zone": {name: zones[name]["top"] for name, _, _ in ZONES},
        "backup_red_by_zone": {name: zones[name]["backup"] for name, _, _ in ZONES},
        "backup_blue": zones["蓝球(1-16)"]["backup"],
        "bule_red": [n for name, _, _ in ZONES for n in zones[name]["bule"]],
        "bule_blue": zones["蓝球(1-16)"]["bule"],
    }}

def _zn(n):
    return 0 if n <= 11 else (1 if n <= 22 else 2)

def _cnt_in(win, n, is_blue):
    if is_blue:
        return sum(1 for r in win if r["蓝球"] == n)
    return sum(1 for r in win for x in r["红球"] if x == n)

def combined_recommend(long_win, short_win):
    """综合推荐：综合分 = 长窗口出现次数 + 2×短窗口出现次数，红球每区至少1个、最多3个。"""
    score = {n: _cnt_in(long_win, n, False) + 2 * _cnt_in(short_win, n, False) for n in range(1, 34)}
    zone_cnt = {}
    red = []
    for lo, hi in [(1, 11), (12, 22), (23, 33)]:
        n = max(range(lo, hi + 1), key=lambda x: score[x])
        red.append(n)
        z = _zn(n)
        zone_cnt[z] = zone_cnt.get(z, 0) + 1
    for n, s in sorted(score.items(), key=lambda kv: -kv[1]):
        if len(red) >= 6:
            break
        z = _zn(n)
        if n in red or zone_cnt.get(z, 0) >= 3:
            continue
        red.append(n)
        zone_cnt[z] = zone_cnt.get(z, 0) + 1
    blue = max(range(1, 17), key=lambda n: _cnt_in(long_win, n, True) + 2 * _cnt_in(short_win, n, True))
    return {"red": sorted(red), "blue": blue}

def analyze(target_issue):
    rows = STATE["rows"]
    if not rows:
        return {"ok": False, "msg": "数据未加载，请先刷新"}
    if not re.fullmatch(r"\d{7}", target_issue):
        return {"ok": False, "msg": "期号格式应为7位数字，如 2026091"}
    idx = next((i for i, r in enumerate(rows) if r["期号"] == target_issue), None)
    if idx is not None:
        long_win = rows[max(0, idx - 528):idx]
        short_win = rows[max(0, idx - 16):idx]
        anchor = idx
        target_draw = {"红球": rows[idx]["红球"], "蓝球": rows[idx]["蓝球"],
                       "开奖日期": rows[idx]["开奖日期"], "星期": rows[idx]["星期"]}
    else:
        long_win = rows[-528:]
        short_win = rows[-16:]
        anchor = len(rows)
        target_draw = None
    if not long_win:
        return {"ok": False, "msg": "历史数据不足，无法分析"}
    long_res = analyze_window(rows, long_win, anchor)
    short_res = analyze_window(rows, short_win, anchor) if short_win else long_res
    combined = combined_recommend(long_win, short_win)
    out = {"ok": True, "target_issue": target_issue, "target_draw": target_draw,
           "window": {"start": long_win[0]["期号"], "end": long_win[-1]["期号"], "count": len(long_win)},
           "zones": long_res["zones"], "recommend": long_res["recommend"],
           "rounds": {
               "long": {"window": {"start": long_win[0]["期号"], "end": long_win[-1]["期号"], "count": len(long_win)},
                        "recommend": long_res["recommend"]},
               "short": {"window": {"start": short_win[0]["期号"], "end": short_win[-1]["期号"], "count": len(short_win)},
                         "recommend": short_res["recommend"], "zones": short_res["zones"]},
               "combined": {"red": combined["red"], "blue": combined["blue"]},
           }}
    latest = rows[-1]
    out["latest"] = {"期号": latest["期号"], "开奖日期": latest["开奖日期"],
                     "红球": latest["红球"], "蓝球": latest["蓝球"]}
    out["refresh_time"] = STATE["refresh_time"]
    # 机器学习（决策树 + 随机森林）
    if ML_MODELS["models"] is None:
        with ML_LOCK:
            if ML_MODELS["models"] is None:
                ML_MODELS["models"] = ml_model.train(rows)
    t_target = idx - 1 if idx is not None else len(rows) - 1
    out["ml"] = ml_model.predict(rows, ML_MODELS["models"], t_target)
    return out

# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/" or u.path == "/index.html":
            if not os.path.exists(HTML_PATH):
                self._send(404, b"index.html not found", "text/plain; charset=utf-8")
                return
            with open(HTML_PATH, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif u.path == "/api/data":
            rows = STATE["rows"]
            latest = rows[-1] if rows else None
            self._json({"latest": latest, "refresh_time": STATE["refresh_time"],
                        "total": len(rows)})
        elif u.path.startswith("/img/"):
            fp = os.path.abspath(os.path.join(BASE, u.path.lstrip("/")))
            if fp.startswith(os.path.abspath(BASE)) and os.path.isfile(fp):
                ext = os.path.splitext(fp)[1].lstrip(".").lower()
                ctype = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                         "gif": "image/gif", "svg": "image/svg+xml"}.get(ext, "application/octet-stream")
                with open(fp, "rb") as f:
                    self._send(200, f.read(), ctype)
            else:
                self._send(404, b"Not Found", "text/plain; charset=utf-8")
        elif u.path == "/api/analyze":
            q = parse_qs(u.query)
            issue = q.get("issue", [""])[0]
            self._json(analyze(issue))
        else:
            self._send(404, b"Not Found", "text/plain; charset=utf-8")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/refresh":
            try:
                refresh()
                rows = STATE["rows"]
                latest = rows[-1] if rows else None
                self._json({"ok": True, "latest": latest, "refresh_time": STATE["refresh_time"],
                            "total": len(rows)})
            except Exception as e:
                self._json({"ok": False, "msg": str(e)}, 500)
        else:
            self._send(404, b"Not Found", "text/plain; charset=utf-8")

    def log_message(self, fmt, *args):
        pass

def find_free_port(start=8765):
    for port in range(start, start + 20):
        try:
            with socket.socket() as s:
                s.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
    return start

def main():
    if os.path.exists(CSV_PATH):
        STATE["rows"] = load_rows()
        STATE["refresh_time"] = "本地数据加载"
    else:
        print("未找到本地数据，正在从官网下载…")
        refresh()
    def warmup():
        try:
            with ML_LOCK:
                if ML_MODELS["models"] is None:
                    ML_MODELS["models"] = ml_model.train(STATE["rows"])
            print("机器学习模型已就绪（训练 %.1f 秒）" % ML_MODELS["models"]["train_sec"])
        except Exception as e:
            print("模型预热失败：%s" % e)
    threading.Thread(target=warmup, daemon=True).start()
    port = find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d" % port
    print("工具已启动：%s  （按 Ctrl+C 退出）" % url)
    if os.environ.get("SSQ_NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")

if __name__ == "__main__":
    main()
