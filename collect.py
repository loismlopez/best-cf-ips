#!/usr/bin/env python3
"""收集 IPv4：拉 sources.txt、提 IP:port、去重、分流 104 开头段.

用法：
    python3 collect.py [--sources sources.txt] [--out-dir .]

输出（同一目录）：
    candidates_all.txt     全部去重后 (ip,port)
    candidates_no104.txt   去掉 104.* 后
    candidates_only104.txt 仅 104.* 

格式：每行 `IP:port`，不带 # 注释，scan.py 直接认。
端口保留源文件里的值（443 / 8443 等），没写端口默认 443。
同一 IP 不同端口算两条（CF 优选里 443 和 8443 是不同入口）。
"""
import argparse
import re
import urllib.request
from pathlib import Path

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# 行内 IP 后可选 :port，例如 1.2.3.4:8443#xxx
IP_PORT_RE = re.compile(r"\b((?:\d{1,3}\.){3}\d{1,3})(?::(\d{1,5}))?")


def valid_ip(s: str) -> bool:
    try:
        return all(0 <= int(o) <= 255 for o in s.split("."))
    except ValueError:
        return False


def extract(text: str) -> set[tuple[str, int]]:
    out: set[tuple[str, int]] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for m in IP_PORT_RE.finditer(line):
            ip, port = m.group(1), m.group(2)
            if not valid_ip(ip):
                continue
            p = int(port) if port else 443
            if 1 <= p <= 65535:
                out.add((ip, p))
    return out


def extract_region(text: str, tag: str) -> set[tuple[str, int]]:
    """只提行里带地区标记的 IP（源站自己标的地区优选）。
    注意：这是源站标签，不是实测落点。实测落点由 scan.py 的 trace 定，
    从美国 Runner 测，同一 IP 也可能落 US。"""
    out: set[tuple[str, int]] = set()
    for line in text.splitlines():
        if tag not in line.upper() and not any(w in line for w in ("日本", "美国", "新加坡")):
            continue
        if tag == "JP" and "日本" not in line and "JP" not in line.upper():
            continue
        if tag == "US" and "美国" not in line and "US" not in line.upper():
            continue
        if tag == "SG" and "新加坡" not in line and "SG" not in line.upper() and "sg" not in line.lower():
            continue
        for m in IP_PORT_RE.finditer(line):
            ip, port = m.group(1), m.group(2)
            if not valid_ip(ip):
                continue
            p = int(port) if port else 443
            if 1 <= p <= 65535:
                out.add((ip, p))
    return out


def fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="sources.txt")
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_ips: set[tuple[str, int]] = set()
    jp_ips: set[tuple[str, int]] = set()
    us_ips: set[tuple[str, int]] = set()
    sg_ips: set[tuple[str, int]] = set()
    for line in Path(args.sources).read_text(encoding="utf-8").splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        try:
            text = fetch(url)
            got = extract(text)
        except Exception as e:  # noqa: BLE001 - 单源失败不杀整批
            print(f"FAIL {url}: {e}")
            continue
        print(f"OK {url}: {len(got)}")
        all_ips |= got
        jp_ips |= extract_region(text, "JP")
        us_ips |= extract_region(text, "US")
        sg_ips |= extract_region(text, "SG")

    no104 = {(ip, p) for ip, p in all_ips if not ip.startswith("104.")}
    only104 = {(ip, p) for ip, p in all_ips if ip.startswith("104.")}
    for name, s in [
        ("candidates_all.txt", all_ips),
        ("candidates_no104.txt", no104),
        ("candidates_only104.txt", only104),
        ("candidates_jp.txt", jp_ips),
        ("candidates_us.txt", us_ips),
        ("candidates_sg.txt", sg_ips),
    ]:
        p = out_dir / name
        p.write_text("".join(f"{ip}:{port}\n" for ip, port in sorted(s)), encoding="utf-8")
        print(f"{name}: {len(s)}")
    print(f"total unique (ip,port): {len(all_ips)}  no104={len(no104)} only104={len(only104)} jp={len(jp_ips)} us={len(us_ips)} sg={len(sg_ips)}")


if __name__ == "__main__":
    main()
