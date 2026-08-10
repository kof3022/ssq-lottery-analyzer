# -*- coding: utf-8 -*-
"""下载双色球全量历史 + 最近100期，保存CSV并校验完整性。"""
import urllib.request, json, csv, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
URL = ("https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/"
       "findDrawNotice?name=ssq&issueCount=3000")
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/",
}

def fetch():
    req = urllib.request.Request(URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("state") != 0 or not data.get("result"):
        raise RuntimeError("接口返回异常")
    return data["result"]

def normalize(item):
    code = str(item["code"])
    date = str(item["date"]).split("(")[0].strip()
    week = str(item.get("week", "")).strip()
    reds = [int(x) for x in re.findall(r"\d+", item["red"])]
    return {"期号": code, "开奖日期": date, "星期": week,
            "红1": reds[0], "红2": reds[1], "红3": reds[2],
            "红4": reds[3], "红5": reds[4], "红6": reds[5], "蓝球": int(item["blue"])}

def save(rows, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

def year_seq(code):
    return int(code[:4]), int(code[4:])

def validate(rows):
    errors = []
    codes = [r["期号"] for r in rows]
    if len(set(codes)) != len(codes):
        errors.append("存在重复期号")
    for i in range(1, len(rows)):
        y1, s1 = year_seq(rows[i-1]["期号"]); y2, s2 = year_seq(rows[i]["期号"])
        if y1 == y2:
            if s2 - s1 != 1:
                errors.append("期号不连续: %s -> %s" % (rows[i-1]["期号"], rows[i]["期号"]))
        elif y2 != y1 + 1:
            errors.append("期号跨年异常: %s -> %s" % (rows[i-1]["期号"], rows[i]["期号"]))
    for r in rows:
        reds = [r["红%d" % i] for i in range(1, 7)]
        if len(set(reds)) != 6 or any(x < 1 or x > 33 for x in reds):
            errors.append("红球异常: %s" % r["期号"])
        if r["蓝球"] < 1 or r["蓝球"] > 16:
            errors.append("蓝球异常: %s" % r["期号"])
    return errors

def main():
    raw = fetch()
    rows = sorted((normalize(x) for x in raw), key=lambda r: r["期号"])
    full_path = os.path.join(BASE, "双色球开奖数据_全量历史.csv")
    last100_path = os.path.join(BASE, "双色球开奖数据_最近100期.csv")
    save(rows, full_path)
    save(rows[-100:], last100_path)
    errs = validate(rows)
    print("全量: %d 期 -> %s" % (len(rows), full_path))
    print("最近100期 -> %s" % last100_path)
    print("最早: %s (%s)  最新: %s (%s)" % (rows[0]["期号"], rows[0]["开奖日期"], rows[-1]["期号"], rows[-1]["开奖日期"]))
    print("校验: %s" % ("通过，无异常" if not errs else "发现问题: " + "; ".join(errs[:8])))

if __name__ == "__main__":
    main()
