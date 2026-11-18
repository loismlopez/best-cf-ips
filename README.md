# 同类项目：Cloudflare 优选 IP API（IPv4）

复刻 `LancelotRar/best-cf-ips` 的 `best-cf-ip-scanned-top*.txt`。
只用 Python 标准库，无需 Go、无需装包。

## 它到底是怎么做出来的

原仓库里**没有扫描器**，只有一个 star-history workflow，扫描在仓外跑完再 push。
每次提交都是 `top cf ips updated … [skip ci]`，5 个文件全量重写，
top20 ⊂ top50 ⊂ top100 ⊂ top200 ⊂ top400，首行带时间戳。
README 写“每 6 小时更新、按延迟排序”，实测 commit 间隔约 10 小时。

本项目把仓外那一步补齐，分三段：

```
sources.txt（7 个公开优选源）
    ↓ collect.py：拉取 → 正则提 IPv4:port → 去重 → 分流 104.*
candidates_all.txt（104 条，按 IP:port 计；去重 IP 是 102 个）/ no104（89）/ only104（15）  ← 2026-11-18 实测数
    ↓ scan.py：TCP connect 测延迟（默认 3 轮）→ /cdn-cgi/trace 取国家码 → 排序
result.csv（全量：延迟/丢包/速度/colo/国家）
    ↓ 切片
best-cf-ip-scanned-top20/50/100/200/400.txt  ← 格式与原项目一致
```

### 两种“优选”别混了

| 文件 | 做法 | 排序依据 |
| --- | --- | --- |
| `best-cf-ip-collected.txt`（原项目已取消） | 聚合多个公开源，去重 + 标国家 | 上游顺序，无实测 |
| `best-cf-ip-scanned-top*.txt`（本项目复刻） | 实测候选 IP 的延迟 | **延迟升序** |

另外一个常见工具 `XIU2/CloudflareSpeedTest` 默认是另一口径：
先延迟排序，再对前 N 名下载测速，最后**按下载速度排序**。
想复刻 Lancelot 就别用默认：`scan.py` 默认只测延迟、不测下载；
想按速度排，再加 `--speed-test 20 --sort speed`。

### 104 开头段

`过滤 104 开头`有两种意思，结果差很多，`collect.py` 三种都出，你自己选：

- `candidates_all.txt`：104 条（按 IP:port 计，同一 IP 的 443/8443 算两条）
- `candidates_no104.txt`：去掉 104.*，剩 89 条
- `candidates_only104.txt`：只留 104.*，剩 15 条

而原项目 top100 里 104.* 占 78 条。`run.sh` 顶部 `FILTER` 改一行即可切换。

## 部署在 GitHub 上自动运行（默认）

推一次，之后每 6 小时 GitHub Actions 自动跑 `collect.py + scan.py`，
有变化自动提交，不用你家电脑开着。

```bash
git init && git add . && git commit -m "init"
git remote add origin git@github.com:<你>/<仓>.git
git push -u origin main
```

推完去仓库 Actions 页点一次 `update` → `Run workflow` 手动跑一遍，
确认绿了、文件生成了，之后定时任务就接管了。
cron 是 `0 */6 * * *`，在 `.github/workflows/update.yml` 里改。

之后别人就能直接用 raw 链接当优选源，例如：

```
https://raw.githubusercontent.com/<你>/<仓>/main/best-cf-ip-scanned-top100.txt
```

注意：排名是 GitHub Runner 那条线路（Azure 机房）测出的，
不是你家宽带的排名。这是部署在 GitHub 上自动运行的代价。

## 本地跑（只用来调试，不参与定时）

```bash
chmod +x run.sh
./run.sh                 # 默认 FILTER=all
FILTER=no104 ./run.sh    # 去掉 104.* 再测
```

输出：`result.csv` + `best-cf-ip-scanned-top20.txt` 等。
只想要前 20 名做下载测速复核：

```bash
python3 scan.py --input candidates_all.txt --speed-test 20 --sort speed
```

本地别和 Actions 同时推同一批文件，会打架。定时只走 Actions。

## 接到 CFPilot / edgetunnel / cfnew

- CFPilot 桌面“优选 → 手动优选上传”：把 `best-cf-ip-scanned-top100.txt` 的内容粘进去回填。
- edgetunnel 自定义订阅汇聚 / cfnew 优选 IP 来源 URL：直接填上面那条 raw 链接。
- 只取前 20/50 就够用，多选重复，没必要全量都填。

## 坑

- 延迟极低（<1ms）= 走了代理，先关代理再测，否则排名全是假的。
- 并发别太高，HTTPing 本质是扫描行为，并发过高会被运营商/CF 临时限流，
  表现为后半程可用 IP 越来越少，停一会儿又恢复。
- 源会变：`sources.txt` 里的地址失效、内容格式变了，`collect.py` 会打印 `FAIL`，
  不杀整批，但总数会掉，跑完看一眼计数。
- 国家码来自 `/cdn-cgi/trace` 的 `loc=`，是 IP 实际落到的机房国家，
  同一个 IP 不同运营商解析出的国家可能不同，这是 Cloudflare anycast 的正常现象。
- trace 失败的 IP 记 `N/A`，只留在 `result.csv` 里备查，不进 top 文件。
  首跑 72 条里就有 7 条 N/A，全是最慢的 141–199ms 那批。
