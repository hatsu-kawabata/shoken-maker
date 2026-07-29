#!/usr/bin/env python3
"""IndexNowでURLを検索エンジンに直接通知する。

Googleはサイトマップとクロール待ち行列に依存する(2026-07-26時点で当サイトの
sitemapは3日以上『取得できませんでした』のまま)。IndexNowはURLを直接受け取る経路で、
新規ドメインのクロール予算の制約を受けない。api.indexnow.org に出すと参加エンジン
(Bing・Yandex・Seznam・Naver)へ配信される。ChatGPT/CopilotはBing索引を引くので、
ここが通ることはLLMO仮説(H1)の分母づくりでもある。

使い方:
  python3 scripts/indexnow.py --changed    # lastmod台帳で今日変わったURLだけ通知
  python3 scripts/indexnow.py --all        # sitemap.xmlの全URLを通知
  python3 scripts/indexnow.py --only /pages/ranking/senior/ ...  # 指定URLだけ通知
  python3 scripts/indexnow.py --all --dry-run

--only がある理由: --changed は台帳の「最新日付」でURLを選ぶので、同じ日に2回
ビルドすると1回目に通知済みのURLまで再び対象に入る。実際に変わったのが数本の
ときは、変わった分だけを明示して送る(不要な再通知はスパム信号になりうる)。
"""
import argparse
import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
MANIFEST = Path(__file__).resolve().parent / "lastmod.json"
SITE = "https://shoken-maker.vercel.app"
HOST = "shoken-maker.vercel.app"
# 公開が前提の鍵(web/{KEY}.txt として配信し、それが所有権の証明になる)
KEY = "42f540e0e565ee0164d56ad410aa23f1"
ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH = 10000
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def write_key_file() -> Path:
    p = WEB / f"{KEY}.txt"
    p.write_text(KEY + "\n")
    return p


def verify_key_live() -> None:
    """通知の前に本番の鍵ファイルを実際に引く。

    鍵が配信されていなければIndexNowは403で弾く。先に自分で確かめておくと、
    『送ったのに入らない』の原因が鍵なのか索引側なのかを取り違えずに済む。
    """
    url = f"{SITE}/{KEY}.txt"
    with urllib.request.urlopen(url, timeout=30) as r:
        body = r.read().decode().strip()
    if r.status != 200 or body != KEY:
        raise SystemExit(f"鍵ファイルが本番で確認できない: {url} status={r.status} body={body!r}")
    print(f"鍵ファイル確認: {url} = {body}")


def sitemap_urls() -> list[str]:
    root = ET.parse(WEB / "sitemap.xml").getroot()
    return [u.find(f"{NS}loc").text for u in root.findall(f"{NS}url")]


def changed_urls(date: str | None) -> list[str]:
    """lastmod台帳で日付が最新(=直近の公開で本文が変わった)URLだけ返す。"""
    m = json.loads(MANIFEST.read_text())
    target = date or max(v["d"] for v in m.values())
    return [u for u, v in m.items() if v["d"] == target]


def submit(urls: list[str], dry_run: bool) -> None:
    for i in range(0, len(urls), BATCH):
        chunk = urls[i:i + BATCH]
        payload = {"host": HOST, "key": KEY, "keyLocation": f"{SITE}/{KEY}.txt",
                   "urlList": chunk}
        if dry_run:
            print(f"[dry-run] {len(chunk)} urls -> {ENDPOINT} (先頭: {chunk[0]})")
            continue
        req = urllib.request.Request(
            ENDPOINT, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                print(f"{len(chunk)} urls -> {r.status} {r.reason}")
        except urllib.error.HTTPError as e:
            print(f"{len(chunk)} urls -> {e.code} {e.reason}: {e.read().decode()[:300]}")
            raise SystemExit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="sitemap.xmlの全URL")
    g.add_argument("--changed", action="store_true", help="lastmod台帳で最新日付のURLのみ")
    g.add_argument("--only", nargs="+", metavar="PATH",
                   help="指定したパス(またはURL)だけ通知する")
    ap.add_argument("--date", help="--changedで対象にする日付(既定=台帳の最新日)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    p = write_key_file()
    if args.only:
        urls = [u if u.startswith("http") else f"{SITE}{u}" for u in args.only]
    else:
        urls = sitemap_urls() if args.all else changed_urls(args.date)
    print(f"鍵ファイル: {p.relative_to(ROOT)} / 通知対象 {len(urls)} URL")
    if not urls:
        print("対象なし")
        return
    if not args.dry_run:
        verify_key_live()
    submit(urls, args.dry_run)


if __name__ == "__main__":
    main()
