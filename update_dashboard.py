#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行业日报仪表盘（股市 / 金融 / 互联网）—— 每日自动更新脚本（自包含）。
流程：抓取当日行业新闻 -> 整理入本地数据集 -> 重新生成单文件 HTML 仪表盘 -> 上传 GitHub 并推送邮件。
      -> 通过 GitHub Contents API 上传到仓库（带重试）。
所有状态都保存在本脚本同目录（D:/ai-hot-daily-automation），不依赖任何会话目录。
"""
import json, os, sys, time, base64, argparse, tempfile, urllib.request, urllib.error, datetime
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "db_slim.json")
TOKEN_PATH = os.path.join(HERE, "github_token.txt")
OUT_PATH = os.path.join(HERE, "index.html")
REPO = "3529083364chatgpt-debug/caijing-daily"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
SECTION_ORDER = ["股市", "金融", "互联网"]
MAX_KEEP = 120  # 最多保留最近 N 期日报，避免无限膨胀

# 把临时目录指到 D:，避免写入已满的 C: 盘
_TMP = os.path.join(HERE, "tmp")
os.makedirs(_TMP, exist_ok=True)
tempfile.tempdir = _TMP
for _v in ("TMPDIR", "TEMP", "TMP"):
    os.environ[_v] = _TMP


# ---------------- network ----------------
def http_get(url, retries=4, timeout=60):
    last = None
    for a in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


# ---------------- slim helpers ----------------
def trunc(s, n=60):
    if not s:
        return ""
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def clean_source(n):
    return (n or "未知来源").replace("（RSS）", "").replace("(RSS)", "").strip()


def slim_day(d):
    date_ = d.get("date")
    raw = {s["label"]: s.get("items", []) for s in d.get("sections", [])}
    lead = d.get("lead")
    lead_slim = None
    if isinstance(lead, dict) and lead.get("title"):
        lead_slim = {"t": lead.get("title"), "p": trunc(lead.get("leadParagraph", ""), 120)}
    secs = {}
    for lbl in SECTION_ORDER:
        its = []
        for it in raw.get(lbl, []):
            its.append({
                "t": it.get("title", ""),
                "s": trunc(it.get("summary", "")),
                "src": clean_source(it.get("sourceName", "")),
                "u": it.get("sourceUrl", "#"),
            })
        secs[lbl] = its
    return date_, {"lead": lead_slim, "s": secs}


# ---------------- db io ----------------
def load_db():
    if os.path.exists(DB_PATH):
        try:
            return json.load(open(DB_PATH, encoding="utf-8"))
        except Exception:
            pass
    return {"start": None, "end": None, "days": {}}


def save_db(db):
    json.dump(db, open(DB_PATH, "w", encoding="utf-8"), ensure_ascii=False)


# ---------------- github upload ----------------
def upload(html, retries=5):
    token = os.environ.get("GH_TOKEN") or open(TOKEN_PATH, encoding="utf-8").read().strip()

    def api(method, url, data=None):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "token " + token)
        req.add_header("Accept", "application/vnd.github.v3+json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        return urllib.request.urlopen(req, timeout=120)

    sha = None
    try:
        cur = json.loads(api("GET", f"https://api.github.com/repos/{REPO}/contents/index.html").read())
        sha = cur["sha"]
    except Exception as e:
        print("  [upload] index.html not present yet, will create:", repr(e)[:60])

    b64 = base64.b64encode(html.encode("utf-8")).decode()
    body = json.dumps({
        "message": "Daily auto-update: append today's finance digest",
        "content": b64, "sha": sha, "branch": "main",
    }).encode("utf-8")
    last = None
    for a in range(1, retries + 1):
        try:
            r = api("PUT", f"https://api.github.com/repos/{REPO}/contents/index.html", body)
            j = json.loads(r.read().decode())
            return j["commit"]["sha"]
        except Exception as e:
            last = e
            print("  upload retry", a, repr(e)[:80]); time.sleep(3)
    raise last


# ---------------- html template ----------------
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>行业日报仪表盘</title>
<style>
  :root{
    --bg:#f3f4f8; --panel:#ffffff; --ink:#15171c; --muted:#6b7280;
    --line:#e9ebf1; --shadow:0 1px 3px rgba(16,24,40,.05),0 14px 34px rgba(16,24,40,.09);
    --radius:18px; --ac:#4f46e5;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html{scroll-behavior:smooth}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
    background:var(--bg);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
  a{color:inherit}
  .wrap{max-width:1120px;margin:0 auto;padding:0 20px}

  /* Hero */
  .hero{background:linear-gradient(135deg,#3730a3 0%,#6d28d9 46%,#0ea5e9 100%);color:#fff;padding:40px 0 30px;position:relative;overflow:hidden}
  .hero::after{content:"";position:absolute;inset:0;background:
    radial-gradient(620px 240px at 88% -20%,rgba(255,255,255,.22),transparent),
    radial-gradient(480px 260px at 6% 130%,rgba(255,255,255,.14),transparent)}
  .hero .wrap{position:relative;z-index:1}
  .eyebrow{font-size:13px;letter-spacing:.2em;text-transform:uppercase;opacity:.9;font-weight:700}
  .hero h1{font-size:clamp(28px,5vw,46px);font-weight:800;margin:8px 0 6px;letter-spacing:-.6px}
  .hero .meta{opacity:.94;font-size:15px;margin-top:8px}
  .hero .meta b{font-weight:700}
  .stats{display:grid;grid-template-columns:1.1fr repeat(5,1fr);gap:12px;margin-top:24px}
  .stat{background:rgba(255,255,255,.16);backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,.28);
    border-radius:16px;padding:16px 12px;text-align:center;transition:transform .2s,background .2s}
  .stat:hover{transform:translateY(-3px);background:rgba(255,255,255,.24)}
  .stat.total .num{font-size:42px}
  .stat .num{font-size:30px;font-weight:800;line-height:1}
  .stat .lbl{font-size:12px;opacity:.92;margin-top:7px;line-height:1.35}
  .stat .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle}

  /* Controls bar */
  .controls{position:sticky;top:0;z-index:25;background:rgba(255,255,255,.94);backdrop-filter:blur(10px);
    border-bottom:1px solid var(--line);box-shadow:0 2px 10px rgba(16,24,40,.04)}
  .controls .wrap{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:12px 20px}
  .tabs{display:inline-flex;background:#eef1f7;border-radius:12px;padding:4px}
  .tabs button{border:0;background:transparent;font:inherit;font-weight:700;font-size:14px;color:var(--muted);
    padding:8px 16px;border-radius:9px;cursor:pointer;transition:.15s}
  .tabs button.on{background:#fff;color:var(--ink);box-shadow:0 1px 3px rgba(16,24,40,.12)}
  .navbtns{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
  .btn{border:1px solid var(--line);background:#fff;border-radius:9px;padding:7px 13px;font:inherit;font-size:13px;
    font-weight:600;color:var(--ink);cursor:pointer;transition:.15s}
  .btn:hover{border-color:#cbd2e0;background:#fafbff}
  .btn.primary{background:#4f46e5;border-color:#4f46e5;color:#fff}
  .btn.primary:hover{filter:brightness(1.05)}
  select.date{font:inherit;font-size:13px;font-weight:600;padding:7px 10px;border:1px solid var(--line);
    border-radius:9px;background:#fff;color:var(--ink);cursor:pointer;max-width:220px}
  .rangetag{font-size:13px;color:var(--muted);font-weight:600;margin-left:auto}

  /* Section nav */
  .nav{position:sticky;top:57px;z-index:20;background:rgba(255,255,255,.92);backdrop-filter:blur(10px);
    border-bottom:1px solid var(--line)}
  .nav .wrap{display:flex;gap:8px;overflow-x:auto;padding:10px 20px;scrollbar-width:none}
  .nav .wrap::-webkit-scrollbar{display:none}
  .nav a{flex:0 0 auto;text-decoration:none;font-size:13px;font-weight:600;color:var(--muted);
    padding:7px 13px;border-radius:999px;border:1px solid var(--line);background:#fff;white-space:nowrap;transition:.15s}
  .nav a:hover{color:var(--ink);border-color:#cbd2e0}
  .nav a .c{display:inline-block;min-width:20px;text-align:center;margin-left:6px;font-size:11px;
    background:#eef1f7;color:#475069;border-radius:999px;padding:0 6px}

  /* Leads panel */
  .leads{margin:26px 0 4px;background:#fff;border:1px solid var(--line);border-radius:var(--radius);
    padding:18px 20px;box-shadow:var(--shadow)}
  .leads h3{font-size:15px;font-weight:800;margin-bottom:12px;display:flex;align-items:center;gap:8px}
  .leads ol{list-style:none;display:grid;gap:10px}
  .leads li{display:flex;gap:12px;align-items:baseline;padding-bottom:10px;border-bottom:1px dashed var(--line)}
  .leads li:last-child{border-bottom:0;padding-bottom:0}
  .leads .ld{font-size:12px;font-weight:700;color:#fff;background:#7c3aed;border-radius:7px;padding:2px 8px;white-space:nowrap}
  .leads .lt{font-size:14px;font-weight:600}
  .leads .lp{font-size:12.5px;color:var(--muted);margin-top:2px}

  /* Sections */
  section.block{padding:30px 0 8px;scroll-margin-top:118px}
  .sec-head{display:flex;align-items:center;gap:12px;margin-bottom:18px}
  .sec-head .ic{font-size:24px}
  .sec-head h2{font-size:21px;font-weight:800;letter-spacing:-.3px}
  .sec-head .badge{margin-left:auto;font-size:13px;font-weight:700;color:#fff;border-radius:999px;padding:4px 14px;box-shadow:0 4px 12px rgba(16,24,40,.18)}
  .sec-head .rule{flex:1;height:1px;background:var(--line)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
  .card{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--ac,#4f46e5);border-radius:var(--radius);padding:18px 20px;
    box-shadow:var(--shadow);display:flex;flex-direction:column;gap:10px;transition:transform .18s,box-shadow .18s}
  .card:hover{transform:translateY(-4px);box-shadow:0 6px 14px rgba(16,24,40,.07),0 22px 46px rgba(16,24,40,.13)}
  .card .top{display:flex;align-items:center;gap:10px}
  .num{flex:0 0 auto;width:30px;height:30px;border-radius:9px;color:#fff;font-weight:800;font-size:14px;
    display:flex;align-items:center;justify-content:center}
  .chip{font-size:12px;font-weight:600;color:#475069;background:#eef1f7;border-radius:999px;padding:3px 10px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
  .card h3{font-size:15.5px;font-weight:700;line-height:1.45}
  .card p{font-size:13.5px;color:#475069;line-height:1.6}
  .card .go{margin-top:auto;display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:700;
    text-decoration:none;align-self:flex-start;padding:7px 13px;border-radius:10px;background:#f3f4f8;transition:.15s}
  .card .go:hover{filter:brightness(.97)}
  .empty{grid-column:1/-1;background:#fff;border:1px dashed var(--line);border-radius:var(--radius);padding:28px;
    text-align:center;color:var(--muted);font-size:14px}

  footer{margin-top:34px;padding:24px 0 40px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
  footer .wrap{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;justify-content:space-between}
  .totpill{font-weight:800;color:var(--ink)}
  #top{position:fixed;right:20px;bottom:22px;width:44px;height:44px;border-radius:50%;border:none;cursor:pointer;
    background:#4f46e5;color:#fff;font-size:20px;box-shadow:0 8px 22px rgba(79,70,229,.4);opacity:0;pointer-events:none;transition:.2s;z-index:30}
  #top.show{opacity:1;pointer-events:auto}
  @media(max-width:760px){
    .stats{grid-template-columns:repeat(3,1fr)}
    .stat.total{grid-column:1/-1}
    .rangetag{margin-left:0;width:100%}
    .nav{top:113px}
  }
</style>
</head>
<body>
  <header class="hero"><div class="wrap">
    <div class="eyebrow">行业日报 · 每日 / 每周 / 每月（股市 / 金融 / 互联网）</div>
    <h1 id="hTitle">—</h1>
    <div class="meta" id="hMeta">—</div>
    <div class="stats" id="stats"></div>
  </div></header>

  <div class="controls"><div class="wrap">
    <div class="tabs" id="tabs">
      <button data-mode="day" class="on">日报</button>
      <button data-mode="week">周报</button>
      <button data-mode="month">月报</button>
    </div>
    <div class="navbtns" id="navbtns"></div>
    <span class="rangetag" id="rangetag"></span>
  </div></div>

  <nav class="nav"><div class="wrap" id="nav"></div></nav>

  <main class="wrap" id="main"></main>

  <footer><div class="wrap">
    <span>本视图共 <span class="totpill" id="footTotal"></span> 条 · 数据源：<span id="footSrc"></span></span>
    <span id="footCov"></span>
  </div></footer>

  <button id="top" title="返回顶部">↑</button>

<script>
const DB = __DB__;
const SECTIONS = ["股市","金融","互联网"];
const ICON = {"股市":"📈","金融":"🏦","互联网":"💻"};
const ACCENT = {"股市":"#e11d48","金融":"#059669","互联网":"#2563eb"};
const DATES = Object.keys(DB.days).sort();
const esc = s => (s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

let state = { mode:"day", cursor: DB.end };

/* ---- date helpers ---- */
function parse(d){const [y,m,a]=d.split("-").map(Number);return new Date(y,m-1,a);}
function ymd(dt){return dt.getFullYear()+"-"+String(dt.getMonth()+1).padStart(2,"0")+"-"+String(dt.getDate()).padStart(2,"0");}
function fmtCn(d){const dt=parse(d);return dt.getFullYear()+"年"+(dt.getMonth()+1)+"月"+dt.getDate()+"日";}
function wkCN(d){return "星期"+"日一二三四五六"[parse(d).getDay()];}
function addDays(d,n){const dt=parse(d);dt.setDate(dt.getDate()+n);return ymd(dt);}
function mondayOf(d){const dt=parse(d);const wd=dt.getDay();const diff=(wd+6)%7;const m=new Date(dt);m.setDate(dt.getDate()-diff);return ymd(m);}
function isoWeek(d){const dt=parse(d);const t=new Date(Date.UTC(dt.getFullYear(),dt.getMonth(),dt.getDate()));const day=t.getUTCDay()||7;t.setUTCDate(t.getUTCDate()-day+3);const firstThu=new Date(Date.UTC(t.getUTCFullYear(),0,4));const wk=1+Math.round((t-firstThu)/86400000/7);return {year:t.getUTCFullYear(),wk};}
function emptySections(){const o={};SECTIONS.forEach(l=>o[l]=[]);return o;}
function count(s){return SECTIONS.reduce((a,l)=>a+s[l].length,0);}
function merge(days){
  const out=emptySections();const seen=new Set();
  days.forEach(d=>{const day=DB.days[d];if(!day)return;SECTIONS.forEach(l=>{
    (day.s[l]||[]).forEach(it=>{if(!seen.has(it.t)){seen.add(it.t);out[l].push(it);}});
  });});
  return out;
}

/* ---- view computation ---- */
function getView(){
  if(state.mode==="day"){
    const d=state.cursor, day=DB.days[d];
    const s = day?day.s:emptySections();
    return {title:fmtCn(d)+" "+wkCN(d), sub:"当日行业精选日报", secs:s,
            leads: (day&&day.lead)?[day.lead]:[], total:count(s), kind:"day"};
  }
  if(state.mode==="week"){
    const mon=mondayOf(state.cursor); const ds=[];
    for(let i=0;i<7;i++){const dd=addDays(mon,i);if(DB.days[dd])ds.push(dd);}
    const m=merge(ds); const {year,wk}=isoWeek(mon);
    const leads=ds.map(dd=>DB.days[dd].lead).filter(Boolean);
    return {title:year+"年 第"+wk+"周", sub:fmtCn(mon)+" – "+fmtCn(addDays(mon,6))+"（含 "+ds.length+" 期日报）",
            secs:m, leads, total:count(m), kind:"week"};
  }
  const dt=parse(state.cursor), y=dt.getFullYear(), mo=dt.getMonth()+1;
  const pfx=y+"-"+String(mo).padStart(2,"0");
  const ds=DATES.filter(d=>d.startsWith(pfx));
  const m=merge(ds);
  const leads=ds.map(dd=>DB.days[dd].lead).filter(Boolean);
  return {title:y+"年"+mo+"月", sub:"本月共 "+ds.length+" 期行业日报精选合集", secs:m, leads, total:count(m), kind:"month"};
}

/* ---- render ---- */
function render(){
  const v=getView();
  document.getElementById("hTitle").textContent=v.title;
  document.getElementById("hMeta").textContent=v.sub;
  let sh='<div class="stat total"><div class="num">'+v.total+'</div><div class="lbl">本视图总条数</div></div>';
  SECTIONS.forEach(l=>{sh+='<div class="stat"><div class="num" style="color:'+ACCENT[l]+'">'+v.secs[l].length+'</div><div class="lbl"><span class="dot" style="background:'+ACCENT[l]+'"></span>'+esc(l)+'</div></div>';});
  document.getElementById("stats").innerHTML=sh;
  renderControls();
  let nh="";SECTIONS.forEach((l,i)=>{nh+='<a href="#sec-'+i+'" data-i="'+i+'">'+ICON[l]+" "+esc(l)+'<span class="c">'+v.secs[l].length+'</span></a>';});
  document.getElementById("nav").innerHTML=nh;
  let n=0;SECTIONS.forEach(l=>{v.secs[l].forEach(it=>{it.n=++n;});});
  let body="";
  if(v.leads&&v.leads.length){
    body+='<div class="leads"><h3>📌 本期头条</h3><ol>';
    v.leads.forEach(ld=>{body+='<li><span class="ld">头条</span><div><div class="lt">'+esc(ld.t)+'</div>'+(ld.p?'<div class="lp">'+esc(ld.p)+'</div>':'')+'</div></li>';});
    body+='</ol></div>';
  }
  SECTIONS.forEach((l,i)=>{
    const items=v.secs[l];let cards;
    if(!items.length){cards='<div class="empty">本版块本期暂无条目</div>';}
    else{
      cards='<div class="grid">';
      items.forEach(it=>{cards+='<article class="card" style="--ac:'+ACCENT[l]+'"><div class="top"><span class="num" style="background:'+ACCENT[l]+'">'+it.n+'</span><span class="chip" title="'+esc(it.src)+'">'+esc(it.src)+'</span></div><h3>'+esc(it.t)+'</h3>'+(it.s?'<p>'+esc(it.s)+'</p>':'')+'<a class="go" style="color:'+ACCENT[l]+'" href="'+esc(it.u)+'" target="_blank" rel="noopener noreferrer">阅读原文 →</a></article>';});
      cards+='</div>';
    }
    body+='<section class="block" id="sec-'+i+'"><div class="sec-head"><span class="ic">'+ICON[l]+'</span><h2>'+esc(l)+'</h2><span class="rule"></span><span class="badge" style="background:'+ACCENT[l]+'">'+items.length+' 条</span></div>'+cards+'</section>';
  });
  document.getElementById("main").innerHTML=body;
  document.getElementById("footTotal").textContent=v.total;
  document.getElementById("footSrc").textContent="权威行业媒体 / 交易所 / 监管机构 多元聚合";
  document.getElementById("footCov").textContent="数据覆盖 "+DB.start+" ~ "+DB.end+"（共 "+DATES.length+" 期日报，已内嵌）";
  initObserver();
}

function renderControls(){
  const nb=document.getElementById("navbtns");const tag=document.getElementById("rangetag");
  let html="";
  if(state.mode==="day"){
    const i=DATES.indexOf(state.cursor);
    html+='<button class="btn" id="prev">‹ 上一天</button>';
    html+='<select class="date" id="pick">';
    DATES.slice().reverse().forEach(d=>{html+='<option value="'+d+'"'+(d===state.cursor?' selected':'')+'>'+fmtCn(d)+" "+wkCN(d)+'</option>';});
    html+='</select>';
    html+='<button class="btn" id="next">下一天 ›</button>';
    html+='<button class="btn primary" id="latest">最新</button>';
    tag.textContent="日报模式：从下方选择任意日期查看当日精选";
  }else if(state.mode==="week"){
    html+='<button class="btn" id="prev">‹ 上一周</button>';
    html+='<button class="btn" id="next">下一周 ›</button>';
    html+='<button class="btn primary" id="latest">最近一周</button>';
    const mon=mondayOf(state.cursor);tag.textContent="周报模式：合并该周各日报精选（"+fmtCn(mon)+" 起）";
  }else{
    html+='<button class="btn" id="prev">‹ 上个月</button>';
    html+='<button class="btn" id="next">下个月 ›</button>';
    html+='<button class="btn primary" id="latest">最近一月</button>';
    const dt=parse(state.cursor);tag.textContent="月报模式：合并当月各日报精选（"+dt.getFullYear()+"年"+(dt.getMonth()+1)+"月）";
  }
  nb.innerHTML=html;
  const prev=document.getElementById("prev"),next=document.getElementById("next"),latest=document.getElementById("latest");
  if(state.mode==="day"){
    prev.onclick=()=>{const i=DATES.indexOf(state.cursor);if(i>0)state.cursor=DATES[i-1];render();window.scrollTo({top:0,behavior:"smooth"});};
    next.onclick=()=>{const i=DATES.indexOf(state.cursor);if(i<DATES.length-1)state.cursor=DATES[i+1];render();window.scrollTo({top:0,behavior:"smooth"});};
    document.getElementById("pick").onchange=e=>{state.cursor=e.target.value;render();};
  }else if(state.mode==="week"){
    prev.onclick=()=>{state.cursor=addDays(mondayOf(state.cursor),-7);render();window.scrollTo({top:0,behavior:"smooth"});};
    next.onclick=()=>{state.cursor=addDays(mondayOf(state.cursor),7);render();window.scrollTo({top:0,behavior:"smooth"});};
  }else{
    const dt=parse(state.cursor);const nd=new Date(dt.getFullYear(),dt.getMonth()-1,1);prev.onclick=()=>{state.cursor=ymd(nd);render();window.scrollTo({top:0,behavior:"smooth"});};
    const nd2=new Date(dt.getFullYear(),dt.getMonth()+1,1);next.onclick=()=>{state.cursor=ymd(nd2);render();window.scrollTo({top:0,behavior:"smooth"});};
  }
  latest.onclick=()=>{state.cursor=DB.end;render();window.scrollTo({top:0,behavior:"smooth"});};
}

document.querySelectorAll("#tabs button").forEach(b=>{
  b.onclick=()=>{
    document.querySelectorAll("#tabs button").forEach(x=>x.classList.remove("on"));
    b.classList.add("on");state.mode=b.dataset.mode;render();window.scrollTo({top:0,behavior:"smooth"});
  };
});

let obs=null;
function initObserver(){
  if(obs)obs.disconnect();
  const links=[...document.querySelectorAll("#nav a")];
  function onIntersect(es){es.forEach(function(e){if(e.isIntersecting){var i=e.target.id.split("-")[1];
    links.forEach(function(a){var on=a.dataset.i===i;a.style.background=on?ACCENT[SECTIONS[i]]:"transparent";a.style.borderColor=on?"transparent":"var(--line)";a.style.color=on?"#fff":"var(--muted)";});}});}
  obs=new IntersectionObserver(onIntersect,{rootMargin:"-45% 0px -50% 0px"});
  SECTIONS.forEach((l,i)=>obs.observe(document.getElementById("sec-"+i)));
}

const topBtn=document.getElementById("top");
window.addEventListener("scroll",()=>topBtn.classList.toggle("show",window.scrollY>400));
topBtn.addEventListener("click",()=>window.scrollTo({top:0,behavior:"smooth"}));

render();
</script>
</body>
</html>
"""


def build_html(db):
    db_json = json.dumps(db, ensure_ascii=False, separators=(",", ":"))
    return HTML.replace("__DB__", db_json)


# ---------------- cloud db sync & mail ----------------
def put_file(repo_path, content, message, branch="main"):
    """Create/update any file in the GitHub repo via Contents API. Returns commit sha."""
    token = os.environ.get("GH_TOKEN") or open(TOKEN_PATH, encoding="utf-8").read().strip()

    def api(method, url, data=None):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "token " + token)
        req.add_header("Accept", "application/vnd.github.v3+json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        return urllib.request.urlopen(req, timeout=120)

    url = f"https://api.github.com/repos/{REPO}/contents/{repo_path}"
    sha = None
    try:
        cur = json.loads(api("GET", url).read())
        sha = cur["sha"]
    except Exception:
        pass
    b64 = base64.b64encode(content.encode("utf-8")).decode()
    body = {"message": message, "content": b64, "branch": branch}
    if sha:
        body["sha"] = sha
    data = json.dumps(body).encode("utf-8")
    for a in range(1, 6):
        try:
            r = api("PUT", url, data)
            return json.loads(r.read().decode())["commit"]["sha"]
        except Exception as e:
            print("  put_file retry", a, repr(e)[:80]); time.sleep(3)
    raise RuntimeError("put_file failed: " + repo_path)


def pull_db_if_missing():
    """In a fresh cloud sandbox there is no local db_slim.json -> fetch it from GitHub."""
    if os.path.exists(DB_PATH):
        return
    token = os.environ.get("GH_TOKEN") or open(TOKEN_PATH, encoding="utf-8").read().strip()
    url = f"https://api.github.com/repos/{REPO}/contents/db_slim.json"
    try:
        req = urllib.request.Request(url, headers={
            "Authorization": "token " + token,
            "Accept": "application/vnd.github.v3+json"})
        j = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
        content = base64.b64decode(j["content"]).decode("utf-8")
        json.dump(json.loads(content), open(DB_PATH, "w", encoding="utf-8"), ensure_ascii=False)
        print("[0] pulled db_slim.json from GitHub")
    except Exception as e:
        print("[0] no remote db yet, starting fresh:", repr(e)[:80])


def _dedupe(seq):
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]


def _daily(today, db):
    ds = sorted(db["days"].keys())[-2:]
    secs = {s: [] for s in SECTION_ORDER}
    for d in ds:
        for s in SECTION_ORDER:
            for it in db["days"][d].get("s", {}).get(s, []):
                if it.get("t"):
                    secs[s].append(it["t"])
    for s in secs:
        secs[s] = _dedupe(secs[s])[:6]
    label = (ds[0] + " ~ " + ds[-1]) if ds else today.isoformat()
    return {"type": "daily", "name": "行业日报", "header": "今日行业看点", "date_label": label, "secs": secs}


def _weekly(today, db):
    cut = today - datetime.timedelta(days=7)
    ds = [d for d in sorted(db["days"].keys()) if date.fromisoformat(d) >= cut]
    agg = {s: [] for s in SECTION_ORDER}
    for d in ds:
        for s in SECTION_ORDER:
            for it in db["days"][d].get("s", {}).get(s, []):
                if it.get("t"):
                    agg[s].append(it["t"])
    for s in agg:
        agg[s] = _dedupe(agg[s])[:6]
    label = (ds[0] + " ~ " + ds[-1]) if ds else ""
    return {"type": "weekly", "name": "行业周报", "header": "上周行业看点", "date_label": label, "secs": agg}


def _monthly(today, db):
    ym = (today.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
    ds = [d for d in sorted(db["days"].keys()) if d.startswith(ym)]
    agg = {s: [] for s in SECTION_ORDER}
    for d in ds:
        for s in SECTION_ORDER:
            for it in db["days"][d].get("s", {}).get(s, []):
                if it.get("t"):
                    agg[s].append(it["t"])
    for s in agg:
        agg[s] = _dedupe(agg[s])[:6]
    return {"type": "monthly", "name": "行业月报", "header": "上月行业看点", "date_label": ym, "secs": agg}


def make_report(today, db):
    out = [_daily(today, db)]
    if today.weekday() == 0:
        out.append(_weekly(today, db))
    if today.day == 1:
        out.append(_monthly(today, db))
    return out


def esc_html(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_mail_html(name, report):
    LINK = "https://3529083364chatgpt-debug.github.io/caijing-daily/"
    sec_html = ""
    for sec in SECTION_ORDER:
        items = report["secs"].get(sec, [])
        if not items:
            continue
        lines = "".join("· " + esc_html(t) + "<br>" for t in items)
        sec_html += ('<p style="margin:0 0 10px;"><strong style="color:#374151;">'
                     + esc_html(sec) + "</strong><br>" + lines + "</p>")
    subj_kind = {"daily": "今天的行业日报", "weekly": "上周的行业周报",
                 "monthly": "上月的行业月报"}[report["type"]]
    return ('<p style="font-size:15px;line-height:1.7;color:#222;">' + esc_html(name)
            + "早上好，" + subj_kind + "来啦，请您查收。</p>\n"
            '<p><a href="' + LINK + '" style="color:#2563eb;font-size:15px;font-weight:600;">'
            "👉 点击查看：行业日报仪表盘</a></p>\n"
            '<p style="margin:14px 0 6px;font-size:14px;font-weight:700;color:#111;">📌 '
            + esc_html(report["header"]) + "（" + esc_html(report["date_label"]) + "）</p>\n"
            + sec_html
            + '<p style="font-size:13px;color:#888;margin-top:14px;">用浏览器打开上方蓝色链接即可查看当日及历史日报，支持日报 / 周报 / 月报切换。</p>')


# 收件人配置：mode="std" 沿用原标题格式；mode="linjie" 使用个性化标题（林杰专属）
RECEIVERS = [
    {"to": "3529083364@qq.com",     "name": "小陶", "mode": "std"},
    {"to": "2750214411@qq.com",     "name": "永川", "mode": "std"},
    {"to": "wanlinjie0913@163.com", "name": "林杰", "mode": "linjie"},
]
# 本报告在邮件中的称呼（林杰个性化标题使用）
REPORT_LABEL = "行业日报"


def send_mail(to_addr, name, report, mode="std"):
    import smtplib
    from email.mime.text import MIMEText
    user = os.environ.get("QQ_SMTP_USER")
    auth = os.environ.get("QQ_SMTP_AUTH")
    if not user or not auth:
        print("  [mail] skip: QQ_SMTP_USER / QQ_SMTP_AUTH not set")
        return False
    if mode == "linjie":
        subject = "林杰早上好鸭，这是今日的 " + REPORT_LABEL + "，请查收"
    else:
        type2subj = {"daily": "今天的行业日报来啦，请您查收",
                     "weekly": "这是上周的行业周报，请您查收",
                     "monthly": "这是上月的行业月报，请您查收"}
        subject = "【" + name + "早上好，" + type2subj[report["type"]] + "】"
    html = build_mail_html(name, report)
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    for a in range(1, 4):
        try:
            with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30) as s:
                s.login(user, auth)
                s.sendmail(user, [to_addr], msg.as_string())
            print("  [mail] sent to " + to_addr + ": " + subject)
            return True
        except Exception as e:
            print("  [mail] retry", a, repr(e)[:80]); time.sleep(3)
    return False


def send_all_reports(db):
    for r in RECEIVERS:
        for report in make_report(date.today(), db):
            send_mail(r["to"], r["name"], report, r.get("mode", "std"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-upload", action="store_true", help="only regenerate locally, do not push to GitHub")
    ap.add_argument("--no-mail", action="store_true", help="skip sending email reports")
    args = ap.parse_args()

    pull_db_if_missing()
    db = load_db()
    print("[1] current days:", len(db["days"]), "range:", db.get("start"), "->", db.get("end"))

    today = date.today().strftime("%Y-%m-%d")
    print("[2] today:", today)

    # 读取由 agent 抓取的当日行业数据（db_slim 当日格式）
    daily_path = os.path.join(HERE, "daily_caijing.json")
    added = 0
    skip_reason = None

    def day_has_content(slim):
        return any((slim.get("s", {}) or {}).get(sec) for sec in SECTION_ORDER)

    if not os.path.exists(daily_path):
        skip_reason = "daily_caijing.json 不存在，今天没有可收录的新闻"
    else:
        try:
            with open(daily_path, encoding="utf-8") as f:
                day_data = json.load(f)
            d = day_data.get("date") or today
            # 日期护栏：只收录当天（最近一天）的新闻，过期/缺失则跳过，避免滞后数据
            if d != today:
                skip_reason = "抓取日期 %s ≠ 今天 %s，疑似滞后数据，已跳过" % (d, today)
            else:
                slim = {"lead": day_data.get("lead"), "s": {}}
                for sec in SECTION_ORDER:
                    slim["s"][sec] = [
                        {"t": it.get("t", ""), "s": trunc(it.get("s", "")),
                         "src": clean_source(it.get("src", "")), "u": it.get("u", "#")}
                        for it in day_data.get("s", {}).get(sec, [])
                    ]
                if not day_has_content(slim):
                    skip_reason = "今天各板块均无有效新闻条目，跳过收录"
                else:
                    db["days"][d] = slim
                    added += 1
                    print("    + added", d)
        except Exception as e:
            skip_reason = "daily_caijing.json 解析失败: " + repr(e)[:60]

    if skip_reason:
        print("    [skip] " + skip_reason)
        print("    [skip] 今天不更新仪表盘、也不推送邮件（避免发送滞后/空数据）")
        return

    # trim to most recent MAX_KEEP
    all_dates = sorted(db["days"].keys())
    if len(all_dates) > MAX_KEEP:
        keep = set(all_dates[-MAX_KEEP:])
        db["days"] = {k: v for k, v in db["days"].items() if k in keep}
        all_dates = sorted(db["days"].keys())
    db["start"] = all_dates[0]
    db["end"] = all_dates[-1]
    save_db(db)
    print("[3] appended:", added, "| total days now:", len(db["days"]), "range:", db["start"], "->", db["end"])

    html = build_html(db)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print("[4] wrote", OUT_PATH, "| bytes:", len(html.encode("utf-8")))

    if args.no_upload:
        print("[5] --no-upload set, skipping GitHub push")
    else:
        sha = upload(html)
        print("[5] uploaded to GitHub, commit:", sha)
        try:
            dbsha = put_file("db_slim.json", json.dumps(db, ensure_ascii=False),
                             "Daily auto-update: sync db_slim.json")
            print("[5b] db_slim.json pushed, commit:", dbsha)
        except Exception as e:
            print("[5b] db_slim.json push failed:", repr(e)[:80])

    if not args.no_mail:
        send_all_reports(db)


if __name__ == "__main__":
    main()
