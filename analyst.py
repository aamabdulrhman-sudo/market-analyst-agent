#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
وكيل محلل السوق الذكي — Smart Market Analyst Agent
وكيل يحلل وضع الشركات في سوق تداول السعودي بناءً على أخبار
وكيل أخبار الأسواق المالية (يعمل على المنفذ 8083 افتراضيًا).

- يجلب أخبار آخر ٢٤ ساعة من وكيل الأخبار.
- يحلل كل شركة مدرجة مذكورة في الأخبار: يُجمّع معنويات أخبارها
  (موزونة بالتقييم، الحداثة، وقوة الخبر).
- ينتج لكل شركة توقعًا: ارتفاع / هبوط / استقرار، مع نسبة ثقة
  وأسباب مأخوذة من عناوين الأخبار ومصادرها.
- يقدم نظرة عامة للسوق: توزيع التوقعات، القطاعات الأكثر تأثرًا،
  وملخص المعنويات.

مبني بالكامل بدون مكتبات خارجية (Python فقط).
"""
import json
import os
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BASE = Path(__file__).resolve().parent
PUBLIC_DIR = BASE / "public"
DATA_DIR = BASE / "data"
ANALYSIS_FILE = DATA_DIR / "analysis.json"

DEFAULT_PORT = 8084
DEFAULT_NEWS_AGENT = os.environ.get("NEWS_AGENT_URL", "http://127.0.0.1:8083")
ANALYSIS_INTERVAL = int(os.environ.get("ANALYSIS_INTERVAL", "10"))  # دقائق

# ---------- قاعدة الشركات المدرجة في السوق السعودي (تداول) ----------
# المفتاح = اسم الشركة الكامل كما يصنّفه وكيل الأخبار، القيمة = بيانات العرض.
TADAWUL = {
    "شركة أرامكو السعودية": {"name": "أرامكو السعودية", "sector": "طاقة"},
    "الشركة السعودية للصناعات الأساسية": {"name": "سابك", "sector": "بتروكيماويات"},
    "شركة التعدين العربية السعودية": {"name": "معادن", "sector": "تعدين"},
    "شركة الاتصالات السعودية": {"name": "stc", "sector": "اتصالات"},
    "شركة اتحاد اتصالات": {"name": "موبايلي", "sector": "اتصالات"},
    "شركة زين السعودية": {"name": "زين", "sector": "اتصالات"},
    "مصرف الراجحي": {"name": "مصرف الراجحي", "sector": "بنوك"},
    "البنك الأهلي السعودي": {"name": "البنك الأهلي", "sector": "بنوك"},
    "بنك الرياض": {"name": "بنك الرياض", "sector": "بنوك"},
    "بنك الجزيرة": {"name": "بنك الجزيرة", "sector": "بنوك"},
    "البنك السعودي الفرنسي": {"name": "البنك السعودي الفرنسي", "sector": "بنوك"},
    "مصرف الإنماء": {"name": "مصرف الإنماء", "sector": "بنوك"},
    "البنك العربي الوطني": {"name": "العربي الوطني", "sector": "بنوك"},
    "شركة دار الأركان للتطوير العقاري": {"name": "دار الأركان", "sector": "عقار"},
    "شركة روشن العقارية": {"name": "روشن", "sector": "عقار"},
    "الشركة السعودية للصناعات الغذائية": {"name": "المراعي", "sector": "أغذية"},
    "الشركة السعودية للأسمدة الكيماوية": {"name": "سافكو", "sector": "أسمدة"},
    "شركة كيان السعودية للبتروكيماويات": {"name": "كيان", "sector": "بتروكيماويات"},
    "شركة ينبع الوطنية للبتروكيماويات": {"name": "ينساب", "sector": "بتروكيماويات"},
    "الشركة السعودية العالمية للبتروكيماويات": {"name": "سبكيم", "sector": "بتروكيماويات"},
    "شركة رابغ للتكرير والبتروكيماويات": {"name": "بترو رابغ", "sector": "طاقة"},
    "الصحراء العالمية للبتروكيماويات": {"name": "الصحراء العالمية", "sector": "بتروكيماويات"},
    "الشركة اللجين للبتروكيماويات": {"name": "اللجين", "sector": "بتروكيماويات"},
    "شركة الكابلات السعودية": {"name": "الكابلات السعودية", "sector": "صناعية"},
    "شركة بوبا العربية للتأمين التعاوني": {"name": "بوبا العربية", "sector": "تأمين"},
    "الشركة التعاونية للتأمين": {"name": "التعاونية للتأمين", "sector": "تأمين"},
    "الشركة العربية للتأمين": {"name": "العربية للتأمين", "sector": "تأمين"},
    "شركة طوكيو مارين العربية": {"name": "طوكيو مارين", "sector": "تأمين"},
    "شركة بن داود القابضة": {"name": "بن داود", "sector": "تجزئة"},
    "شركة أسواق عبدالله العثيم": {"name": "أسواق العثيم", "sector": "تجزئة"},
    "السيف غاليري": {"name": "السيف غاليري", "sector": "تجزئة"},
    "الشركة الخليجية للتدريب والتعليم": {"name": "الخليج للتدريب", "sector": "تعليم"},
    "شركة أسمنت اليمامة": {"name": "أسمنت اليمامة", "sector": "بناء"},
    "شركة أسمنت السعودية": {"name": "أسمنت السعودية", "sector": "بناء"},
    "شركة أسمنت القصيم": {"name": "أسمنت القصيم", "sector": "بناء"},
    "شركة الرعاية الطبية": {"name": "الرعاية الطبية", "sector": "صحة"},
    "المستشفى السعودي الألماني": {"name": "السعودي الألماني", "sector": "صحة"},
    "الشركة الوطنية السعودية للنقل البحري": {"name": "البحري", "sector": "نقل"},
    "شركة السعودية القابضة": {"name": "السعودية القابضة", "sector": "استثمار"},
}

_lock = threading.Lock()
_analysis_lock = threading.Lock()
_news_agent_status = {"ok": None, "last": None, "news_count": 0, "error": None}
_last_analysis = None  # آخر نتيجة تحليل كاملة
_analysis_running = False


# ------------------------- وقت -------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def age_hours(value, fallback=None):
    dt = parse_dt(value) or parse_dt(fallback)
    if dt is None:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)


# ------------------------- تخزين -------------------------
def load_cache() -> dict:
    if ANALYSIS_FILE.exists():
        try:
            return json.loads(ANALYSIS_FILE.read_text("utf-8"))
        except Exception:
            pass
    return None


def save_cache(analysis: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    tmp = ANALYSIS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(ANALYSIS_FILE)


# ------------------------- الاتصال بوكيل الأخبار -------------------------
def _get(url: str, timeout: float = 15.0):
    req = urllib.request.Request(url, headers={"User-Agent": "SmartMarketAnalyst/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_news() -> list:
    """يجلب أخبار آخر ٢٤ ساعة من وكيل الأخبار (دون حد أقصى للعدد)."""
    return _get(DEFAULT_NEWS_AGENT + "/api/news?limit=0&hours=24")


def refresh_news_agent() -> dict:
    """يطلب من وكيل الأخبار جلب جديد من المصادر."""
    return _get(DEFAULT_NEWS_AGENT + "/api/news/refresh", timeout=60.0)


def news_agent_status() -> dict:
    try:
        st = _get(DEFAULT_NEWS_AGENT + "/api/status", timeout=8.0)
        return {"ok": True, "name": st.get("name"), "port": st.get("port"),
                "last_refresh": st.get("last_refresh"), "error": None}
    except Exception as ex:
        return {"ok": False, "name": None, "port": None,
                "last_refresh": None, "error": str(ex)}


# ------------------------- محرك التحليل -------------------------
def analyze(news: list) -> dict:
    """يحلل الأخبار ويبني تقرير الشركات + نظرة السوق."""
    companies = {}

    for n in news:
        for full_name in (n.get("companies") or []):
            meta = TADAWUL.get(full_name)
            if not meta:
                continue  # الشركات غير المدرجة في تداول تُتجاهل في تحليل الشركات
            c = companies.setdefault(full_name, {
                "company": full_name,
                "name": meta["name"],
                "sector": meta["sector"],
                "news": [],
                "score_sum": 0.0,
                "weight_sum": 0.0,
                "pos": 0,
                "neg": 0,
                "neu": 0,
                "strong": 0,
            })
            score = float(n.get("score") or 0)
            rating = float(n.get("rating") or 0)
            strong = bool(n.get("strong"))
            hours = age_hours(n.get("published_at"), n.get("added_at"))
            # أوزان: التقييم (١–١٠)، الحداثة (٤٨ ساعة)، قوة الخبر
            rating_w = min(1.0, rating / 10.0)
            recency_w = max(0.15, 1.0 - hours / 48.0)
            strong_w = 1.4 if strong else 1.0
            w = max(0.05, rating_w * recency_w * strong_w)
            c["score_sum"] += score * w
            c["weight_sum"] += w
            c["news"].append({
                "id": n.get("id"),
                "title": n.get("title"),
                "url": n.get("url"),
                "source": n.get("source"),
                "score": score,
                "rating": rating,
                "category": n.get("category"),
                "strong": strong,
                "published_at": n.get("published_at"),
            })
            cat = n.get("category")
            if cat == "ايجابي":
                c["pos"] += 1
            elif cat == "سلبي":
                c["neg"] += 1
            else:
                c["neu"] += 1
            if strong:
                c["strong"] += 1

    rows = []
    for full_name, c in companies.items():
        if not c["weight_sum"]:
            continue
        avg = c["score_sum"] / c["weight_sum"]
        avg = max(-100.0, min(100.0, avg))
        volume = len(c["news"])
        strong_ratio = (c["strong"] / volume) if volume else 0.0

        if avg >= 15:
            direction, signal = "ارتفاع", "up"
        elif avg <= -15:
            direction, signal = "هبوط", "down"
        else:
            direction, signal = "استقرار", "flat"

        # الثقة: قوة الإشارة + كثافة الأخبار + نسبة الأخبار الحاسمة
        confidence = (
            min(100.0, abs(avg)) * 0.5
            + min(100.0, volume * 12) * 0.3
            + strong_ratio * 100.0 * 0.2
        )
        confidence = max(5.0, min(97.0, round(confidence)))

        # أسباب مختصرة: أقوى الأخبار أولًا
        reasons = sorted(
            c["news"],
            key=lambda x: -abs(x["score"])
        )[:6]

        rows.append({
            "company": full_name,
            "name": c["name"],
            "sector": c["sector"],
            "direction": direction,
            "signal": signal,
            "avg_score": round(avg, 1),
            "confidence": int(confidence),
            "news_count": volume,
            "pos": c["pos"],
            "neg": c["neg"],
            "neu": c["neu"],
            "strong": c["strong"],
            "reasons": [{
                "title": r["title"],
                "url": r["url"],
                "source": r["source"],
                "score": r["score"],
                "rating": r["rating"],
                "category": r["category"],
                "published_at": r["published_at"],
            } for r in reasons],
        })

    # ترتيب: الأقوى إشارة (صعودًا ثم هبوطًا) يليه الاستقرار
    order = {"up": 0, "down": 1, "flat": 2}
    rows.sort(key=lambda r: (order[r["signal"]], -r["confidence"]))

    # نظرة السوق
    up = sum(1 for r in rows if r["signal"] == "up")
    down = sum(1 for r in rows if r["signal"] == "down")
    flat = sum(1 for r in rows if r["signal"] == "flat")

    total_news = len(news)
    cats = {"ايجابي": 0, "سلبي": 0, "محايد": 0}
    for n in news:
        c = n.get("category")
        cats[c] = cats.get(c, 0) + 1
    sentiment = 0
    if total_news:
        sentiment = int(round((cats["ايجابي"] - cats["سلبي"]) / total_news * 100))

    sectors = {}
    for r in rows:
        s = sectors.setdefault(r["sector"], {"sector": r["sector"], "count": 0,
                                              "up": 0, "down": 0, "score_sum": 0.0})
        s["count"] += 1
        s["score_sum"] += r["avg_score"]
        if r["signal"] == "up":
            s["up"] += 1
        elif r["signal"] == "down":
            s["down"] += 1
    for s in sectors.values():
        s["avg_score"] = round(s["score_sum"] / s["count"], 1)
        s["bias"] = ("ارتفاع" if s["avg_score"] >= 15
                     else "هبوط" if s["avg_score"] <= -15 else "استقرار")
    sector_list = sorted(sectors.values(), key=lambda x: abs(x["avg_score"]), reverse=True)

    return {
        "generated_at": now_iso(),
        "news_count": total_news,
        "categories": cats,
        "market_sentiment": sentiment,
        "companies_count": len(rows),
        "up": up,
        "down": down,
        "flat": flat,
        "companies": rows,
        "sectors": sector_list,
    }


def run_analysis() -> dict:
    """ينفذ التحليل كاملًا (جلب + معالجة + حفظ) مع حالة وكيل الأخبار."""
    global _last_analysis, _analysis_running, _news_agent_status
    if not _analysis_lock.acquire(blocking=False):
        return {"ok": False, "message": "تحليل جارٍ بالفعل"}
    try:
        st = news_agent_status()
        _news_agent_status["ok"] = st["ok"]
        _news_agent_status["last"] = now_iso()
        _news_agent_status["error"] = st["error"]
        if not st["ok"]:
            return {"ok": False, "error": "وكيل الأخبار غير متصل",
                    "status": _news_agent_status}
        news = fetch_news()
        _news_agent_status["news_count"] = len(news)
        analysis = analyze(news)
        analysis["news_agent"] = st
        _last_analysis = analysis
        save_cache(analysis)
        return {"ok": True, "analysis": analysis}
    except Exception as ex:
        _news_agent_status["error"] = str(ex)
        return {"ok": False, "error": str(ex), "status": _news_agent_status}
    finally:
        _analysis_lock.release()


def analysis_loop() -> None:
    """تحليل دوري: عند الإقلاع ثم كل ANALYSIS_INTERVAL دقيقة."""
    while True:
        try:
            run_analysis()
        except Exception:
            pass
        time.sleep(max(1, ANALYSIS_INTERVAL) * 60)


# ------------------------- HTTP -------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "SmartMarketAnalyst/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def _path(self) -> list:
        return urlparse(self.path).path.strip("/").split("/")

    def _query(self) -> dict:
        return parse_qs(urlparse(self.path).query)

    def do_GET(self):
        parts = self._path()
        if not parts or parts == [""]:
            self._send_file("index.html")
            return
        if parts[0] == "api":
            self._api("GET", parts)
            return
        name = os.path.basename(parts[-1])
        if len(parts) == 1 and "/" not in name:
            self._send_file(name)
        else:
            self._send(404, {"error": "غير موجود"})

    def do_POST(self):
        self._body = self._read_body()
        parts = self._path()
        if parts and parts[0] == "api":
            self._api("POST", parts)
        else:
            self._send(404, {"error": "غير موجود"})

    def _send_file(self, name):
        path = (PUBLIC_DIR / name).resolve()
        if not path.is_relative_to(PUBLIC_DIR.resolve()) or not path.is_file():
            self._send(404, {"error": "غير موجود"})
            return
        ctype = ("text/html; charset=utf-8" if path.suffix == ".html" else
                 "text/css; charset=utf-8")
        self._send(200, path.read_bytes(), ctype)

    def _api(self, method, parts):
        try:
            self._route(method, parts)
        except Exception as e:
            self._send(500, {"error": f"خطأ داخلي: {e}"})

    def _route(self, method, parts):
        # GET /api/status
        if method == "GET" and parts == ["api", "status"]:
            self._send(200, {
                "ok": True, "name": "وكيل محلل السوق الذكي",
                "port": _port, "version": "1.0",
                "news_agent": DEFAULT_NEWS_AGENT,
                "news_agent_connected": _news_agent_status.get("ok"),
                "last_analysis": (_last_analysis or {}).get("generated_at"),
                "companies_count": ((_last_analysis or {}).get("companies_count") or 0),
                "interval_minutes": ANALYSIS_INTERVAL,
            })
            return

        # POST /api/analyze — إعادة تحليل فوري
        if method == "POST" and parts == ["api", "analyze"]:
            result = run_analysis()
            if result.get("ok"):
                self._send(200, result)
            else:
                self._send(503, result)
            return

        # POST /api/news/refresh — جلب جديد من وكيل الأخبار
        if method == "POST" and parts == ["api", "news", "refresh"]:
            try:
                r = refresh_news_agent()
                self._send(200, r)
            except Exception as ex:
                self._send(503, {"ok": False, "error": str(ex)})
            return

        # GET /api/analysis — آخر تحليل
        if method == "GET" and parts == ["api", "analysis"]:
            data = _last_analysis or load_cache()
            if data is None:
                data = run_analysis().get("analysis")
            if data is None:
                self._send(503, {"ok": False, "error": "لا يوجد تحليل بعد — اضغط زر التحليل"})
                return
            data = dict(data)
            data["news_agent_connected"] = _news_agent_status.get("ok")
            self._send(200, data)
            return

        self._send(404, {"error": "المسار غير موجود"})


def main():
    global _port
    _port = int(os.environ.get("PORT", DEFAULT_PORT))
    # تحليل تلقائي عند الإقلاع + حلقة دورية في الخلفية
    threading.Thread(target=analysis_loop, daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", _port), Handler)
    print("=" * 60)
    print("  وكيل محلل السوق الذكي — Smart Market Analyst")
    print(f"  يستمع على http://0.0.0.0:{_port}")
    print(f"  مصدر الأخبار: {DEFAULT_NEWS_AGENT}")
    print(f"  تحليل تلقائي كل {ANALYSIS_INTERVAL} دقيقة")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
