#!/usr/bin/env python3
"""国土数値情報 S12(駅別乗降客数)から駅マスタ web/data/stations.json を生成する。

入力: raw/S12-24_NumberOfPassengers.geojson (UTF-8版)
名寄せ: 同名駅を300m以内の空間クラスタで統合（事業者横断。例: 新宿=JR+小田急+京王+…）
乗降客数: 最新年(2023, S12_057)。データ有無コード(S12_055)==1の行のみ加算。
         重複コード(S12_054)==2の行は0が入っているのでそのまま足して問題ない。
出力: [{n:駅名, la:緯度, lo:経度, p:乗降客数|null, l:[路線,...]}] 乗降客数降順
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "raw" / "S12-24_NumberOfPassengers.geojson"
OUT = ROOT / "web" / "data" / "stations.json"

CLUSTER_M = 300


def centroid(geom) -> tuple[float, float]:
    coords = geom["coordinates"]
    if geom["type"] == "MultiLineString":
        coords = [pt for line in coords for pt in line]
    lon = sum(p[0] for p in coords) / len(coords)
    lat = sum(p[1] for p in coords) / len(coords)
    return lat, lon


def main() -> None:
    gj = json.loads(SRC.read_text())
    by_name: dict[str, list[dict]] = {}
    for f in gj["features"]:
        p = f["properties"]
        la, lo = centroid(f["geometry"])
        pax = p.get("S12_057") if p.get("S12_055") == 1 else None
        by_name.setdefault(p["S12_001"], []).append(
            {"la": la, "lo": lo, "pax": pax, "line": f'{p["S12_002"]} {p["S12_003"]}'}
        )

    stations = []
    for name, feats in by_name.items():
        clusters: list[dict] = []
        for ft in feats:
            hit = None
            for c in clusters:
                dx = (ft["lo"] - c["lo"]) * 111320 * 0.81  # cos(36°)≈0.81 目安
                dy = (ft["la"] - c["la"]) * 110946
                if dx * dx + dy * dy <= CLUSTER_M * CLUSTER_M:
                    hit = c
                    break
            if hit is None:
                clusters.append({"la": ft["la"], "lo": ft["lo"], "members": [ft]})
            else:
                hit["members"].append(ft)
                n = len(hit["members"])
                hit["la"] += (ft["la"] - hit["la"]) / n
                hit["lo"] += (ft["lo"] - hit["lo"]) / n
        for c in clusters:
            pax_vals = [m["pax"] for m in c["members"] if m["pax"] is not None]
            lines = sorted({m["line"] for m in c["members"]})
            stations.append({
                "n": name,
                "la": round(c["la"], 5),
                "lo": round(c["lo"], 5),
                "p": sum(pax_vals) if pax_vals else None,
                "l": lines,
            })

    stations.sort(key=lambda s: -(s["p"] or 0))
    OUT.write_text(json.dumps(stations, ensure_ascii=False, separators=(",", ":")))
    with_pax = sum(1 for s in stations if s["p"])
    print(f"{len(stations)} stations ({with_pax} with pax) -> {OUT} ({OUT.stat().st_size:,}B)")
    print("top5:", [(s["n"], s["p"]) for s in stations[:5]])


if __name__ == "__main__":
    main()
