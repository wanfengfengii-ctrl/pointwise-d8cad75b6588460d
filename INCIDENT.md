# 早班观测 m 重复入账

早班原拍 m 有 34 脉冲，固定倍率为每脉冲 1/2 毫升。东站首次把 m 移交西站。成功回包丢失，两站重开后，各站都报了 17 毫升。应当只在西站计入一次。

```text
python3 -B -m unittest tests.test_transfer.TransferTests.test_lost_reply_after_receipt
```

以下核账值均按东、西站顺序列出。

| 事件 | 正常台账 | 同一事件下的领取结果 |
| --- | --- | --- |
| 西站隔离收件，移交仍待决 | (17, 0) | 无成功回执，东站不能撤下原件。 |
| 首次移交生效，成功回包丢失 | (0, 17) | 西站可按首次回执领取完整 m，重投返回同一结果。 |
| 西站将 m 返还东站，再投递第一次回执并重投第一次请求 | (17, 0) | 当前报告只列返还产生的新任次，第一次回执仍可按原号领取。 |

在返还场景中，故障版本收到旧请求后会再次把西站旧任次列入班报。若东站已撤下原交出副本，重投则可能领不到已存在的首次回执。原事故、待决和返还场景可分别核对。

```text
python3 -B -m unittest tests.test_transfer.TransferTests.test_pending_receipt tests.test_transfer.TransferTests.test_return_then_replay tests.test_incident
python3 -B check_project.py
python3 -B scenario.py demo
```
