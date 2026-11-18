# 澄湾双站观测归档

澄湾流量试验中心的采样员按仪表、班次、录制段及拍位入册。归档员可将原件移交至另一站复核。值班质控员按现任责任站核对交班量，夜班复核员按号领取原件和过去已经签发的交班单。

## 运行

在项目根目录使用 Python 3.11 执行完整业务回归和演示。运行清单位于 `.pointwise-runtime.json`。

```text
python3 -B check_project.py
python3 -B scenario.py demo
```

演示从 `samples/` 读取固定的早班录制和移交请求，在临时目录创建两个站库。倍率为 1/2 毫升每脉冲。34 脉冲为 17 毫升，0 脉冲为数值零，显式缺测有独立计数。演示核对移交前签发、移交生效后丢回包、双站重开、撤件后西站领取、原件返还、原请求重投和原单读取。故障场景和单独核验入口见 `INCIDENT.md`。

## Python 接口

`station_store.Archives(east_path, west_path, request_home='east')` 持有两个不同的 SQLite 文件路径。站名固定为 `east`、`west`。`initialize_station(station)` 可分别建库，`initialize()` 依次初始化两站。对已有站库重复初始化保留用户数据。重开时以相同文件和请求号登记站构造新的 `Archives` 即可。请求号登记只绑定请求身份，每次业务写入只提交所属的一站。

| 入口 | 输入及返回 |
| --- | --- |
| `capture.calibration.register_calibration` | `(archives, station, instrument, revision, numerator, denominator)`，返回固定正倍率修订。等价重登返回同一修订，修改同号修订会拒绝。 |
| `capture.ingest.record` | `(archives, station, shift, recording, instrument, slot, revision, pulses)`，返回不可变 `Observation`，含 `record_id`、`episode` 和 `origin`。拍位及脉冲是非负整数，`None` 表示缺测。同拍相同内容可重投，冲突或已撤下的原拍拒绝重写。 |
| `dispatch.request.transfer_request` | `(archives, RequestIdentity(number, record_id, source, destination, episode))`，成功返回 `TransferReceipt`，含固定回执号、接收任次、原请求及原件。可用原请求续投，错任次、同号异参及同任次的竞争请求拒绝。 |
| `receive.receipts.take_receipt` | `(archives, station, receipt_id)`，在签发该回执的接收站领取固定结果。未知回执抛出 `ReceiptNotFound`。 |
| `dispatch.retire.retire` | `(archives, station, episode, receipt_id)`，撤下与成功回执匹配的旧交出副本。重复执行同一次合法撤件安全，未决和错配请求抛出 `TransferRejected`。 |
| `tally.current.current` | `(archives, shift)`，返回覆盖两站的 `ShiftTally`。每一现任原拍按脉冲乘固定标定换算。明细按东、西站序及原拍排序，行、站和整班的量用 `Fraction`。空班次仍有两个零汇总站。归属无法确认时抛出 `CustodyUnavailable`。 |
| `edition.issue.issue` | `(archives, station, sheet_id, result)`，`result` 可为已核定 `ShiftTally` 或返回该结果的无参调用。返回 `IssueReceipt`。相同固定单重投可领取原回执，单号冲突拒绝。核账不可用或提交失败时无新单和成功回执。 |
| `edition.read.read_sheet`、`edition.export.export_sheet` | `(archives, station, sheet_id)`，按号返回固定 `ShiftSheet` 或其确定性 JSON。未知单号抛出 `SheetNotFound`。导出保留原拍、任次、逐行量、合计与缺测，计量值以 `[分子, 分母]` 表示。 |

## 业务边界和可控端口

采集校验失败抛出 `ObservationRejected`。确认仍待裁决时，旧责任站独计且领不到成功回执。确认已经生效时，新站独计，成功回执须能领取完整原件。接收站在交出副本撤下后仍能独立交付原件。返还使用新任次，旧请求和迟到结果不得改变其归属。已签交班单按号读回签发时的原量、缺测和逐行来源。归属所需的事实不可读或读到的区间不一致时，核账应重试或报告暂不可用。

`transfer_request` 的可选 `checkpoint(stage)` 可在 `after_grant`、`after_receipt`、`before_decision_commit` 和 `before_reply` 注入中断。正常业务中，`after_receipt` 表示原件已隔离收存、移交仍待决。`before_decision_commit` 中断后仍应待决。`before_reply` 表示移交已经生效、成功结果尚未送达。`dispatch.retry.apply_transfer_result(archives, receipt)` 接收迟到回执并核对其固定结果。`current` 的可选 `before_read(station, phase)` 可在 `facts` 或 `decisions` 读取点模拟端口失败或确定性交错。签发的 `before_commit()` 在本次单据及回执写入后、提交前调用。业务冲突可据异常修正输入，端口中断后可重开并按原请求重投。
