"""全国のモニタリングポストの最新値を取得し、アプリ用の軽量JSONを作る。

出典：原子力規制委員会「放射線モニタリング情報共有・公表システム（RAMIS）」 https://www.ramis.nra.go.jp/
（政府標準利用規約 第2.0版に基づき、出典を明記し加工して利用）

- RAMIS の地図画面が使う公開データ（map-means-data-public）から取得する。外部向けの公式APIではないため、
  仕様変更で取得できなくなることがある。その場合は既存のデータを上書きしない（異常終了する）。
- 1つの測定局に過去の記録が複数含まれることがあるため、測定局ごとに最新の値だけを残す。
- GitHub Actions（.github/workflows/monitoring.yml）から1時間ごと（緊急時は10分ごと）に実行する。

使い方： python3 tools/fetch_monitoring.py 出力先.json [normal|emergency]
"""
import gzip
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://www.ramis.nra.go.jp/api/v1/map/map-means-data-public?data_type={}"
UA = "radiation-sim/2.3 (UOEH disaster occupational health; https://github.com/stateishidohc/radiation-sim)"
# data_type → アプリでの区分
TYPES = {
    1: "mp",        # 固定型モニタリングポスト等
    2: "rt",        # リアルタイム線量計・電子線量計
    3: "mp",        # 港湾等
    5: "portable",  # 可搬型モニタリングポスト
    6: "mp",
    7: "car",       # 走行サーベイ
}
JST = timezone(timedelta(hours=9))


def fetch(t):
    req = urllib.request.Request(API.format(t), headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    for attempt in range(3):
        try:
            raw = urllib.request.urlopen(req, timeout=60).read()
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
            return json.loads(raw).get("data", [])
        except Exception as e:  # 一時的な失敗は少し待って再試行
            if attempt == 2:
                raise
            print(f"retry type {t}: {e}", file=sys.stderr)
            time.sleep(10)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "monitoring.json"
    mode = sys.argv[2] if len(sys.argv) > 2 else "normal"
    latest = {}
    for t, kind in TYPES.items():
        for s in fetch(t):
            if s.get("latitude") is None or s.get("longitude") is None:
                continue
            key = s.get("obs_station_unique_code") or s.get("id")
            cur = latest.get(key)
            if cur is None or (s.get("meas_datetime") or "") > (cur[1].get("meas_datetime") or ""):
                latest[key] = (kind, s)
        time.sleep(1)  # 相手先への負荷を抑える

    stations = []
    for key, (kind, s) in latest.items():
        rate = s.get("air_dose_rate")
        low = s.get("meas_range_low_limit")
        below = rate is not None and low is not None and low >= 0.1 and rate < low  # 例：電子線量計の「0.2未満」
        stations.append([
            key,
            (s.get("display_name") or "").replace("　", " ").strip(),
            round(s["latitude"], 5),
            round(s["longitude"], 5),
            None if rate is None else round(rate, 4),
            low if below else None,
            (s.get("meas_datetime") or "")[:16],
            kind,
        ])
    if len(stations) < 100:  # 取得失敗・仕様変更の疑い。既存データを守るため中断
        sys.exit(f"too few stations: {len(stations)}")
    stations.sort(key=lambda x: x[0])
    doc = {
        "generated": datetime.now(JST).isoformat(timespec="minutes"),
        "mode": mode,
        "source": "原子力規制委員会「放射線モニタリング情報共有・公表システム（RAMIS）」を加工して作成",
        "source_url": "https://www.ramis.nra.go.jp/",
        "fields": ["id", "name", "lat", "lng", "rate_uSv_h", "below_limit", "time", "kind"],
        "stations": stations,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(stations)} stations → {out}")


if __name__ == "__main__":
    main()
