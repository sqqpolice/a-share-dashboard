# -*- coding: utf-8 -*-
"""
A股行业轮动与资金流向监控 · 后端数据抓取脚本
================================================
用途：每天定时运行（或手动运行），从公开接口抓取真实行情，
      计算 MA20 / MACD，产出 data.js（离线双击用）与 data.json（网站模式用）。

数据来源（基于实测可用性分级，见 data.meta 字段如实标注）：
  - 指数实时涨跌      : 腾讯财经 qt.gtimg.cn            【稳定可用，CI/本地均真实】
  - 指数历史日K(近60日): 腾讯财经 web.ifzq.gtimg.cn      【稳定可用，支撑"指数近一周"真实走势】
  - 行业板块涨跌+主力净流入+近30日历史资金流 : 东方财富 push2his.eastmoney.com（fflow/daykline 历史接口）
        【CI 公网直连稳定；公司内网/本机代理对东方财富时通时断，失败则标 snapshot 并沿用内置真实快照】
说明：行业板块"涨跌幅+主力净流入"由东方财富历史资金流接口(push2his)一次读取"最近交易日+过去30日"，
      直接写入 history.json，无需每日累积。腾讯不提供板块报价，故板块级数据依赖东方财富；指数仍由腾讯提供。
      前端用徽章如实区分"真实/示例"。
      北向资金面板已移除：监管 2024/8 起不再实时披露当日净买入，可获取信息有限且无稳定公开源，故不再展示以免误导。

运行：
  python fetch_a股.py            # 在线抓取（需联网）
  python fetch_a股.py --demo     # 离线模式（用内置真实快照验证管线，不联网）
  python fetch_a股.py --serve    # 抓取后顺带起一个本地 http 服务（http://localhost:8000）

依赖：requests（pip install requests）。如缺失会给出提示。
北向资金：监管 2024/8 起不再实时披露当日净买入，公开源信息有限，前端面板已移除。
"""
import os, sys, json, re, datetime, random, time

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 内置真实快照（2026-07-10 收盘，来自腾讯/东方财富公开接口实测）
# 作用：① 离线兜底 ② --demo 验证逻辑。在线抓取成功时会被真实数据整体覆盖。
# ---------------------------------------------------------------------------
SNAP = {
  "date": "2026-07-10",
  "asOf": "2026-07-10 收盘",
  "indices": [
    {"code": "sh000001", "name": "上证指数", "value": 3996.16, "chg": -1.00},
    {"code": "sz399001", "name": "深证成指", "value": 15046.67, "chg": -2.29},
    {"code": "sz399006", "name": "创业板指", "value": 3842.73, "chg": -4.37},
    {"code": "sh000300", "name": "沪深300", "value": 4780.79, "chg": -1.96},
    {"code": "sh000688", "name": "科创50",  "value": 2064.98, "chg": -5.53},
    {"code": "bj899050", "name": "北证50",  "value": 1209.15, "chg": -0.02},
  ],
  "sectors": [
    {"name": "电子",       "bk": "BK1201", "chg": -3.13, "inflow": -435.13},
    {"name": "半导体",     "bk": "BK1036", "chg": -5.38, "inflow": -248.78},
    {"name": "通信设备",   "bk": "BK0448", "chg":  0.13, "inflow":  -70.13},
    {"name": "国防军工",   "bk": "BK1204", "chg":  3.43, "inflow":   77.53},
    {"name": "医药生物",   "bk": "BK1216", "chg":  2.82, "inflow":   40.79},
    {"name": "白酒",       "bk": "BK1277", "chg":  3.64, "inflow":   13.16},
    {"name": "有色金属",   "bk": "BK0478", "chg":  0.17, "inflow":    7.21},
    {"name": "基础化工",   "bk": "BK1206", "chg":  0.06, "inflow":  -37.12},
    {"name": "乘用车",     "bk": "BK1262", "chg":  2.44, "inflow":   11.10},
    {"name": "房地产开发", "bk": "BK0451", "chg":  2.32, "inflow":    0.92},
    {"name": "农林牧渔",   "bk": "BK0433", "chg":  2.38, "inflow":    5.38},
    {"name": "电池",       "bk": "BK1033", "chg": -1.52, "inflow":  -66.57},
    {"name": "光伏",       "bk": "BK1035", "chg":  2.40, "inflow":    1.49},
    {"name": "证券",       "bk": "BK0473", "chg": -1.88, "inflow":  -24.15},
    {"name": "化学制药",   "bk": "BK0075", "chg":  3.22, "inflow":   16.31},
    {"name": "煤炭",       "bk": "BK0437", "chg": -0.11, "inflow":   -1.03},
  ],
  "themes": [
    {"name": "国防军工 +3.43%", "hot": 9.5},
    {"name": "商业航天 +2.70%", "hot": 9.1},
    {"name": "医药/CRO",        "hot": 8.4},
    {"name": "白酒 +3.64%",     "hot": 8.0},
    {"name": "光伏 +2.40%",     "hot": 7.3},
    {"name": "半导体 -5.38%",   "hot": 6.0},
  ],
  "detailTabs": [
    {"name": "半导体",   "bk": "BK1036"},
    {"name": "光伏",     "bk": "BK1035"},
    {"name": "商业航天", "nameMatch": "商业航天"},
    {"name": "新能源车", "nameMatch": "新能源车"},
    {"name": "人工智能", "nameMatch": "人工智能"},
    {"name": "国防军工", "bk": "BK1204"},
    {"name": "电子",     "bk": "BK1201"},
    {"name": "白酒",     "bk": "BK1277"},
    {"name": "医药",     "bk": "BK1216"},
    {"name": "银行",     "nameMatch": "银行"},
    {"name": "煤炭",     "bk": "BK0437"},
    {"name": "电力设备", "bk": "BK1033"},
  ],
  "alloc": [
    {"title": "国防军工 / 商业航天（事件催化 + 资金共振）", "rating": "超配",
     "body": "国防军工当日 +3.43%、主力净流入 77.5 亿居行业首位；商业航天概念资金活跃，卫星互联网、航天装备全线爆发。下半年密集发射窗口与卫星互联网政策支撑，趋势动能强。",
     "tags": ["军工+3.43%", "事件催化密集", "资金共振"]},
    {"title": "医药生物（政策 + 估值修复）", "rating": "标配",
     "body": "医药生物 +2.82%、化学制药 +3.22%；新版国家基本药物目录实施预期纳入创新药，CRO/医疗服务活跃。但短线涨幅已大，建议控仓、逢回调布局。",
     "tags": ["医药+2.82%", "基药目录催化", "涨幅偏大控仓"]},
    {"title": "半导体 / 电子（高位退潮）", "rating": "低配",
     "body": "电子 -3.13%、半导体 -5.38%，主力净流出逾 400 亿，AI 硬件与存储芯片集体重挫。在出现明确止跌信号前维持低配，等待企稳。",
     "tags": ["半导体-5.38%", "主力流出400亿+", "等待止跌"]},
  ],
}

IDX_CODES = [x["code"] for x in SNAP["indices"]]


# ----------------------------- 网络层 -----------------------------
def _session():
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/",
    })
    return s


def em_list(fs, pz=500, fields="f12,f14,f3,f62"):
    """东方财富板块列表（行业 t:2 / 概念 t:3）。返回 [{code,name,chg,inflow}]"""
    s = _session()
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    r = s.get(url, params={
        "pn": 1, "pz": pz, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": "f3", "fs": fs, "fields": fields,
    }, timeout=12)
    m = re.search(r"\((.*)\)", r.text, re.S)
    d = json.loads(m.group(1))
    out = []
    for it in (d.get("data") or {}).get("diff", {}).values():
        out.append({
            "code": it.get("f12"), "name": it.get("f14"),
            "chg": float(it.get("f3") or 0),
            "inflow": round((it.get("f62") or 0) / 1e8, 2),  # 元->亿元
        })
    return out


def tencent_indices(codes):
    """腾讯指数实时。返回 [{code,name,value,chg,time}]"""
    s = _session()
    r = s.get("https://qt.gtimg.cn/q=" + ",".join(codes),
              headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
              timeout=12)
    raw = r.content.decode("gbk", "ignore")
    out = []
    for line in raw.split(";"):
        line = line.strip()
        if not line.startswith("v_") or "=" not in line:
            continue
        code = line[2:line.index("=")]          # 变量名 v_xxxx 中的代码
        payload = line.split("=", 1)[1].strip().strip('"')
        a = payload.split("~")
        if len(a) < 34:
            continue
        try:
            price = float(a[3]); prev = float(a[4])
            chg = round((price / prev - 1) * 100, 2) if prev else 0.0
        except Exception:
            continue
        tm = a[30] if len(a) > 30 and a[30].isdigit() else ""
        # 从腾讯时间字段(YYYYMMDDHHMMSS)精确取出交易日，解决"周末运行却错标为今天"的问题
        date_ymd = ""
        if len(a) > 30 and len(a[30]) >= 8 and a[30][:8].isdigit():
            date_ymd = f"{a[30][:4]}-{a[30][4:6]}-{a[30][6:8]}"
        out.append({"code": code, "name": a[1], "value": price, "chg": chg, "time": tm, "date": date_ymd})
    return out


def tencent_index_kline(code, n=60):
    """腾讯指数历史日K（开/收/高/低/量）。返回 [{d:'YYYY-MM-DD', c:收盘}]。
    用于前端"指数近 N 日真实走势"，腾讯该接口稳定可用。"""
    s = _session()
    r = s.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
              params={"param": f"{code},day,,,{n},qfq"}, timeout=12)
    d = (r.json().get("data") or {}).get(code) or {}
    kl = d.get("day") or d.get("qfqday") or []
    out = []
    for row in kl:
        try:
            out.append({"d": row[0], "c": float(row[2])})
        except Exception:
            pass
    return out


def em_kline(secid, lmt=60):
    """板块 60 日 K 线收盘价。secid 形如 90.BK1036"""
    s = _session()
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    r = s.get(url, params={
        "secid": secid, "fields1": "f1,f2,f3", "fields2": "f51,f53",
        "klt": 101, "fqt": 0, "end": "20500101", "lmt": lmt,
    }, timeout=12)
    m = re.search(r"\((.*)\)", r.text, re.S)
    d = json.loads(m.group(1))
    kl = (d.get("data") or {}).get("klines") or []
    return [float(k.split(",")[1]) for k in kl]


def em_sector_flow(codes, lmt=30, retries=4):
    """东方财富板块历史主力资金流(日K)。对每个 BK 代码取最近 lmt 个交易日。
    返回 {bk: {"name": str, "series": [{d, in(亿), c, chg}], "last": {...}}}。
    依赖 push2his.eastmoney.com（与实时 push2 不同域名；CI 公网直连稳定，本地代理时通时断）。"""
    s = _session()
    out = {}
    for bk in codes:
        secid = "90." + bk
        ok = False
        for attempt in range(retries):
            try:
                r = s.get("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get", params={
                    "lmt": lmt, "klt": 101, "secid": secid,
                    "fields1": "f1,f2,f3,f7",
                    "fields2": "f51,f52,f62,f63",
                    "ut": "b2884a393a59ad64002292a3e90d46a5",
                }, timeout=15)
                d = r.json()
                dd = (d.get("data") or {})
                kl = dd.get("klines") or []
                if not kl:
                    break
                name = dd.get("name") or bk
                series = []
                for k in kl:
                    p = k.split(",")
                    if len(p) < 4:
                        continue
                    try:
                        series.append({
                            "d": p[0],
                            "in": round(float(p[1]) / 1e8, 2),   # 元 -> 亿元
                            "c": float(p[2]),
                            "chg": float(p[3]),
                        })
                    except Exception:
                        continue
                if series:
                    out[bk] = {"name": name, "series": series, "last": series[-1]}
                    ok = True
                    break
            except Exception:
                time.sleep(0.8 * (attempt + 1))
        if not ok:
            print(f"  [warn] 资金流抓取失败 {bk}")
    return out


# ----------------------------- 指标计算 -----------------------------
def ema(arr, n):
    k = 2 / (n + 1)
    out = [arr[0]]
    for i in range(1, len(arr)):
        out.append(arr[i] * k + out[-1] * (1 - k))
    return out


def macd(close, fast=12, slow=26, sig=9):
    eF, eS = ema(close, fast), ema(close, slow)
    dif = [eF[i] - eS[i] for i in range(len(close))]
    dea = ema(dif, sig)
    hist = [(dif[i] - dea[i]) * 2 for i in range(len(close))]
    return {"dif": [round(x, 3) for x in dif],
            "dea": [round(x, 3) for x in dea],
            "hist": [round(x, 3) for x in hist]}


def ma20(close):
    out = []
    for i in range(len(close)):
        out.append(round(sum(close[max(0, i - 19):i + 1]) / min(i + 1, 20), 2))
    return out


# ----------------------------- 合成数据 -----------------------------
def _synthetic_close(seed_name, end_chg, n=60, end=1000.0):
    """离线模式用：生成一条以 end_chg 为终点涨跌幅的确定性序列，仅用于验证管线。"""
    rnd = random.Random(abs(hash(seed_name)) % (2 ** 32))
    drift = (end_chg / 100.0) * 0.22
    p = end / (1 + drift)
    out = []
    for i in range(n):
        p = p * (1 + (rnd.random() - 0.5) * 0.03 + drift / n)
        out.append(round(p, 2))
    return out


def build_data(online=True):
    today = datetime.date.today()
    # meta：如实记录每个模块的数据来源，前端用徽章区分"真实/示例"
    meta = {"indicesSource": "snapshot", "sectorsSource": "snapshot",
            "klineSource": "snapshot",
            "generatedAt": today.strftime("%Y-%m-%d %H:%M")}
    data = {
        "date": today.strftime("%Y-%m-%d"),
        "asOf": today.strftime("%Y-%m-%d") + " 收盘" if online else SNAP["asOf"],
        "indices": SNAP["indices"], "sectors": SNAP["sectors"],
        "themes": SNAP["themes"],
        "detailTabs": [dict(t) for t in SNAP["detailTabs"]],
        "alloc": SNAP["alloc"],
        "source": "demo/offline" if not online else "online-attempt",
        "meta": meta,
        "indexHistory": {},  # 指数近 60 日真实收盘（腾讯），支撑"指数近一周"
    }

    # ---------------- 离线 / 演示模式 ----------------
    if not online:
        by_name = {s["name"]: s for s in SNAP["sectors"]}
        for t in data["detailTabs"]:
            nm = t.get("nameMatch") or t["name"]
            chg = (by_name.get(nm) or {}).get("chg", 0)
            close = _synthetic_close(nm, chg)
            t["series"] = {"close": close, "ma20": ma20(close), "macd": macd(close)}
        # 合成指数历史（仅用于本地验证逻辑，非真实）
        for ix in data["indices"]:
            rnd = random.Random(abs(hash(ix["code"])) % (2 ** 32))
            p = ix["value"] * (1 - ix["chg"] / 100.0)
            hist = []
            for i in range(60):
                d = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
                p = p * (1 + (rnd.random() - 0.5) * 0.02 + (ix["chg"] / 100.0) / 60)
                hist.append({"d": d, "c": round(p, 2)})
            data["indexHistory"][ix["name"]] = hist
        return data

    # ---------------- 在线模式 ----------------
    # 1) 指数：腾讯实时（稳定真实）
    try:
        idx = tencent_indices(IDX_CODES)
        if idx:
            data["indices"] = idx
            meta["indicesSource"] = "tencent-live"
    except Exception as e:
        print("  [warn] 指数抓取失败，沿用快照：", e)

    # 用指数返回的真实交易日校准 date / asOf（周末/休市运行也只取最近交易日）
    if idx:
        trd = idx[0].get("date")
        if trd:
            data["date"] = trd
            data["asOf"] = trd + " 收盘"

    # 2) 指数历史日K：腾讯（真实，立即可用 -> 指数近一周走势）
    try:
        ih = {}
        for code in IDX_CODES:
            kl = tencent_index_kline(code, 60)
            if kl:
                nm = next((x["name"] for x in data["indices"] if x["code"] == code), code)
                ih[nm] = kl
        if ih:
            data["indexHistory"] = ih
    except Exception as e:
        print("  [warn] 指数历史K线失败：", e)

    # 3) 行业板块：东方财富历史资金流接口（push2his fflow/daykline）
    #    一次调用即返回"最近交易日 + 过去30日"的主力净流入/涨跌幅/收盘，
    #    既解决当前板块数据，又直接提供多日历史（history.json 不再靠每日累积）。
    bks = [s["bk"] for s in SNAP["sectors"] if s.get("bk")]
    flow = {}
    sectors_ok = False
    try:
        flow = em_sector_flow(bks, lmt=30)
        if flow:
            sectors_ok = True
            meta["sectorsSource"] = "eastmoney-flow"
    except Exception as e:
        print("  [warn] 板块资金流抓取失败，沿用快照：", e)

    new_sectors = []
    for s in SNAP["sectors"]:
        rec = dict(s)
        f = flow.get(s["bk"])
        if f:
            rec["name"] = f["name"]           # 以接口返回的板块名为准（自校验 BK 代码对错）
            rec["chg"] = f["last"]["chg"]
            rec["inflow"] = f["last"]["in"]
        new_sectors.append(rec)
    data["sectors"] = new_sectors

    # 4) 资金主线（从 16 行业按 涨跌幅+净流入 综合靠前取 6 个）
    if sectors_ok:
        scored = []
        for s in new_sectors:
            score = abs(s["chg"]) + max(0, s["inflow"]) * 0.05
            scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        data["themes"] = [{"name": f"{s['name']} {('+' if s['chg']>=0 else '')}{s['chg']:.2f}%",
                           "hot": round(min(9.9, 5 + score * 0.4), 1)} for _, s in scored[:6]]
    else:
        print("  [warn] 板块未抓取，资金主线沿用快照")

    # 5) 重点板块 K 线 + MACD（直接复用资金流返回的收盘价序列，无需再调独立 K 线接口）
    for t in data["detailTabs"]:
        bk = t.get("bk")
        if not bk and t.get("nameMatch"):
            m = next((s for s in new_sectors
                      if t["nameMatch"] in s["name"] or s["name"] in t["nameMatch"]), None)
            bk = m["bk"] if m else None
        if bk and bk in flow:
            close = [p["c"] for p in flow[bk]["series"]]
            if len(close) >= 26:
                t["bk"] = bk
                t["series"] = {"close": close, "ma20": ma20(close), "macd": macd(close)}
                meta["klineSource"] = "eastmoney-flow"
        elif bk:
            print(f"  [note] 板块 {t.get('name')}({bk}) 无资金流数据，跳过 K 线")

    # 诚实标注数据质量：板块资金流真正抓到才叫 online；否则明确区分
    if sectors_ok:
        data["source"] = "online"                       # 指数+板块都真实
    elif meta["indicesSource"] == "tencent-live":
        data["source"] = "online-index-only"            # 仅指数真实，板块为示例
    else:
        data["source"] = "demo/offline"                 # 全为示例
    data["_flow"] = flow  # 内部字段：供 write_outputs -> update_history 使用，写入前端前会剔除
    return data


def update_history(data, flow):
    """写入 history.json：直接采用东方财富历史资金流接口返回的近 30 个交易日（非累积）。
    每次运行都重新抓取最近 30 个交易日，确保"板块多日资金流向"面板始终有真实的多日数据。
    若接口失败(flow 为空)，用快照生成确定性序列兜底，仅供管线验证。"""
    hist_path = os.path.join(HERE, "history.json")
    pts = {}
    # 16 行业：涨跌幅 + 主力净流入 + 收盘（来自资金流序列）
    for s in data["sectors"]:
        f = flow.get(s.get("bk"))
        if not f:
            continue
        pts[s["name"]] = [{"d": p["d"], "chg": p["chg"], "in": p["in"], "c": p["c"]}
                           for p in f["series"]]
    # 重点板块（带序列）：一并写入，供前端"板块/指数"切换
    for t in data["detailTabs"]:
        if t.get("bk") in flow:
            nm = t.get("nameMatch") or t["name"]
            pts.setdefault(nm, [{"d": p["d"], "chg": p["chg"], "in": p["in"], "c": p["c"]}
                                for p in flow[t["bk"]]["series"]])
    # 兜底：接口失败时用快照生成确定性序列
    if not pts:
        rnd = random.Random(20260710)
        base = datetime.date(2026, 7, 10)
        for s in data["sectors"]:
            ser = []
            for i in range(30):
                d = (base - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
                ser.append({"d": d,
                            "chg": round(s["chg"] + (rnd.random() - 0.5) * 2, 2),
                            "in": round(s["inflow"] + (rnd.random() - 0.5) * 40, 2),
                            "c": round(1000 + (rnd.random() - 0.5) * 50, 2)})
            pts[s["name"]] = ser
    days = len(next(iter(pts.values()))) if pts else 0
    hist = {"updated": data["date"], "points": pts}
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)
    print(f"  [ok] 已更新 history.json（{len(pts)} 个板块时序，每板块 {days} 个交易日）")
    return hist


def write_outputs(data):
    flow = data.pop("_flow", {})  # 剔除内部字段，不写入前端数据
    js = "window.BACKEND_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n"
    with open(os.path.join(HERE, "data.js"), "w", encoding="utf-8") as f:
        f.write(js)
    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"  [ok] 已生成 data.js / data.json（来源={data['source']}，板块={len(data['sectors'])}，K线板块={sum(1 for t in data['detailTabs'] if t.get('series'))}）")
    hist = update_history(data, flow)
    inject_inline(data, hist)


def inject_inline(data, history):
    """把数据内联进 index.html，使页面在 file:// 本地预览或 fetch 失败(fetch 被浏览器拦截)时
    仍能直接显示数据，不依赖外部 data.json / history.json 的 fetch。
    CI 部署时前端仍优先 fetch 当日新鲜文件，仅在 fetch 不可用时回退到内联数据。"""
    html_path = os.path.join(HERE, "index.html")
    if not os.path.exists(html_path):
        return
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    block = ("<!--INLINE_DATA_START-->\n"
             "<script>window.BACKEND_DATA=" + json.dumps(data, ensure_ascii=False) +
             ";window.HISTORY_DATA=" + json.dumps(history, ensure_ascii=False) + ";</script>\n"
             "<!--INLINE_DATA_END-->")
    if "<!--INLINE_DATA_START-->" in html:
        html = re.sub(r"<!--INLINE_DATA_START-->.*?<!--INLINE_DATA_END-->",
                      lambda m: block, html, flags=re.S)
    else:
        html = re.sub(r"<body[^>]*>", lambda m: m.group(0) + "\n" + block, html, count=1)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("  [ok] 已内联数据到 index.html（本地预览/fetch失败时也能显示）")


def main():
    args = sys.argv[1:]
    online = "--demo" not in args
    if "--demo" in args:
        print("== 离线模式（验证管线，不联网）==")
    else:
        print("== 在线抓取真实行情 ==")
    try:
        import requests  # noqa
    except ImportError:
        print("缺少依赖 requests，请先运行：pip install requests")
        sys.exit(1)

    data = build_data(online=online)
    write_outputs(data)

    if "--serve" in args:
        import http.server, socketserver
        os.chdir(HERE)
        port = 8000
        with socketserver.TCPServer(("", port), http.server.SimpleHTTPRequestHandler) as httpd:
            print(f"本地服务已启动：http://localhost:{port}/index.html  （Ctrl+C 停止）")
            httpd.serve_forever()


if __name__ == "__main__":
    main()
