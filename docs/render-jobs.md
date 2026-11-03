# Durable render jobs / 再接続できる描画JOB

Related: [CG #12](https://github.com/flamoris-jp/flamoris-CG/issues/12).

**Submitして戻り、後から同じjob_idで照合する。描画終了までChatGPTのツール呼び出しを保持しない。** CGは既設Flamenco 3のAPIへ委譲し、子プロセスやWorkerを自前で作らない。Cinemaは再開しない。

## Ownership

| Owner | Responsibility |
| --- | --- |
| CG | 登録scene ID、入力制限、依頼ID、受付記録、Flamenco IDとの対応、所有権、結果検証 |
| Flamenco | durable queue、Worker割当、Blenderの起動・終了・回収、実行・停止・リトライ |
| Blender | native sceneと実際の描画 |
| 呼出元 | job_idの保持、次回確認時刻の尊重、完了後の結果転送 |

CG内の新規レンダーファームや常駐プロセスは追加しない。既存Generation Controllerの永続reservation / outcome-unknownと、Kachincoのsubmit/status/exportの境界を比較した。ドメイン固有の実装やプロトコルはコピーせず、対応付けと照合の原則だけを参考にした。MCP Coreはtransport / grantの所有者のまま。

## Application API

`JobApi(RenderJobs(operator_config)).call(request)` がCLIや既設Blender MCPから呼べるデータ境界。新しい公開MCPサーバーやHub catalog登録は含まない。既存の `preview.get` は引き続き読み取り専用で、renderを開始しない。既設Blender MCPの信頼済みPython呼出から同じAPIを利用する。将来の専用MCP tool adapterも、このAPIの上へ既存Coreの権限を適用する。

```json
{"method":"render.submit","params":{
  "request_id":"e13631c9-4b2b-45ba-bb06-16dc7f7eb8de",
  "scene_id":"room-v1", "frames":[1,2,3,4], "chunk_size":24
}}
```

ほかは `job.status` / `job.cancel` / `job.result`（`params: {"job_id":"..."}`）、`job.list`（任意の`limit` 1..100）。不明なmethod/fieldは拒否する。remote requestにパス・URL・Python・shell・任意のjob type・Worker操作は渡せない。Scene登録と保持期限後の削除はローカルoperator CLIだけ。

```python
# このconfigはホスト管理者が設定したもの。リクエストから受け取らない。
from flamoris_cg.render_jobs import JobConfig, RenderJobs
from flamoris_cg.job_api import JobApi
api = JobApi(RenderJobs(JobConfig(**operator_config)))
result = api.call({"method": "job.status", "params": {"job_id": saved_job_id}})
```

`submit` はレンダリングを待たず、local UUIDとbackend UUIDを返す。Managerへの型情報GETと投入POSTだけを行う。HTTP timeoutは既定10秒、設定範囲1..30秒（実機受入れは5秒）。`terminal`がtrueなら確認を止める。通常は`poll_after_seconds`以上待つ。statusには強制refreshで制限を迂回する入口を設けない。

## Persistent authority / unknown outcomes

state_rootは**ホストのローカル永続ディスク**に置く。SQLiteをNAS/SMBへ置かない。private stateとshared outputは別のroot。SQLiteのBEGIN IMMEDIATEとrequest_id UNIQUEで複数クライアントの受付を直列化し、namespace・Manager origin・shared rootのidentityを固定する。

1. 新しいrequest_idのreservationをDBへcommit。
2. Managerのjob-type ETagを取得し、固定`simple-blender-render`を一度だけPOST。
3. backend IDとnamespace/job_id metadataを照合して保存。

同じrequest_id・同じ内容の再送は既存JOBを返す。違う内容なら拒否する。POST応答喪失・不正応答・実行途中のクライアント終了は`unknown`または`submitting`として保持し、**自動再投入しない**。GET一覧のmetadataで唯一の一致が得られた時だけ再接続する。0件や複数件なら不明のままで枠を保持し、operatorに確認させる。0件は「受け付けられていない」証明ではない。

投入前の型情報取得が失敗した場合、POST未実行が分かるため失敗として終える。プロセス強制終了などでこの区別を保存できなかった場合は保守的に不明扱い。自動復元・フレーム再開・成果物の混在はしない。

statusがManagerに接続できなくても、以前の観測を成功・失敗に読み替えない。error、last_checked_at、次の照合時刻を保存する。backendのcreated/updatedは元の値、CGのfinished_atは終了を**観測した時刻**。started_atを推測しない。steps_completed/steps_totalはFlamencoの**タスクstep数**でありフレーム数ではない（プレビュー動画工程もあり得る）。

## Polling and cancellation

- backend GETは同一JOBで最短30秒。再接続してもDBの次回時刻を引き継ぐ。
- HTTP 429/503等はRetry-After（秒またはHTTP日付）より前に再確認しない。最短30秒、エラー時の既定は60秒。GETを短い間隔でループしない。
- 同じcancelの再送は冪等。未確定cancelもbackoffを守る。対象IDをGETしmetadataの所有権を検証してから、そのJOBだけをcanceledへ要求する。
- cancel受付は`canceling`。Managerでcanceledを観測するまで完了扱いしない。完了済みには停止要求を送らない。受付不明のJOBはまず照合し、その後に明示的なcancelを再実行する。
- Manager/Workerのサービス停止・全JOB停止・killall・任意PID停止は実装しない。

CGの処理中にはPopenもローカル子プロセスもないため、今回の「Blender MCPが子を起動して回収しない」経路は使わない。短時間のowner向けnative準備は`subprocess.run(..., timeout=...)`等で明示的に待ち、長いrenderは必ずFlamencoへ渡す。

## Setup and CLI

これはownerの信頼済みローカル環境用APIであり、job_idだけを認証トークンとはしない。host側の既存接続権限、private stateの所有者、固定configが権限境界。Managerへ接続可能な利用者を増やす設定や外部公開は含まない。

operator config（実ホストの値はリポジトリに保存しない）:

```json
{
  "state_root":"/absolute/local-private/cg-jobs",
  "shared_root":"/absolute/flamenco-shared/cg-jobs",
  "manager_url":"http://configured-manager:8080",
  "max_active":1, "poll_seconds":30, "timeout_seconds":10,
  "max_jobs":1000, "max_output_bytes":268435456,
  "max_storage_bytes":2147483648, "retention_seconds":604800
}
```

rootはsymlink/reparseのないowner管理領域にする。Manager URLはoperatorが指定した単一HTTP(S) originで、redirect・ambient proxy・URL埋込credentialを使用しない。worker_tagは任意の管理者設定UUID。max_activeはこのstate内のCG受付枠であり、他のAIランタイムのVRAM排他やホスト全体のGPU所有権ではない。既設Workerの資源方針は変更しない。

```sh
# ownerが作ったnativeだけを開く。準備は描画しない。
blender -b trusted.blend --disable-autoexec --threads 2 --python-exit-code 1 \
  --python blender/prepare_native_job.py -- --scene AuthoredScene \
  --output /NEW/prepared --width 640 --samples 8

python tools/render_jobs.py --config /private/config.json register room-v1 \
  --blend /NEW/prepared/scene.blend --metadata /NEW/prepared/scene.json
python tools/render_jobs.py --config /private/config.json submit --request request.json
python tools/render_jobs.py --config /private/config.json status JOB_UUID
python tools/render_jobs.py --config /private/config.json cancel JOB_UUID
python tools/render_jobs.py --config /private/config.json result JOB_UUID --export /NEW/result.zip
```

登録はnative hashとサイズ、scene名・寸法・fps・範囲を記録し、shared領域へimmutable snapshotを作る。登録後に変更されたnativeは投入を拒否。`prepare_native_job.py`はpackと実際のscene選択をして保存する。登録メタデータはtrusted operatorの宣言で、任意の不審な.blendを安全に実行するsandboxではない。Flamencoの既設Blender起動設定は変えないため、trusted fileだけを登録する。

## Output and retention

最大240フレーム、1920×1080、PNG raw画素予算、実出力byte、native128MiB、保存領域2GiB、未削除1000JOBを既定の制限とする。超過は新規投入・収集を拒否。1万件のrequest tombstoneに達した場合も新しい管理namespaceへの計画的な移行が必要。長時間処理の動作を制限するCPU/GPU quotaではない。

出力はJOBごとのNEW directory。成功時は期待する全フレームの番号・重複・PNGヘッダー寸法・byte上限を照合する。完了状態だけで結果ありとは言わない。失敗・キャンセルでもjob metadataとdiagnosticsをZIPへ収集できる。Flamenco task summaryと最大1件・16KiBのlog tailを含める。完全なログはbackend JOB IDでManager側に保持する。

`job.result`は固定artifact ID `result.zip`・size・SHA-256を返す。ホストのtrusted transferから一括取得する。CG公開APIにbase64分割転送や任意ファイルreadを増やさない。Flamencoが別途作るプレビューMP4は未検証なのでZIPへ自動同梱しない。既存Capture/MCP previewの画像閲覧は別境界。

既定7日以上経過したterminal JOBだけ、ownerが`prune JOB_UUID`を明示実行できる。自動削除はしない。DBには依頼IDのtombstoneを残し、古い依頼の再送で描画を復活させない。active/unknownの削除・scene登録の上書き・共有root削除はしない。Manager UIから同じJOBをrequeueして出力を上書きする運用は避け、CGから新しいrequest IDで新規JOBを作る。

## Batching Blender edits

`blender/build_scene.py --batch examples/render_batch.json` で、既存CG specに最大64操作を適用してから一度だけBlenderで構築する。

対応は`set_location`・`set_scale`・`set_color`・`set_keyframes`（object_idとvalue）、`set_camera`・`set_render`（value）。**全操作をcopy上で検証し、一つでも不正ならBlenderの変更・出力開始前に拒否**。before/afterのspec hash、操作数、変更IDをmanifestに残す。位置の基底値を変える操作は既存keyframeを自動で書き換えない。演技を変える場合はset_keyframesを明示する。

```sh
blender -b --disable-autoexec --threads 2 --python-exit-code 1 \
  --python blender/build_scene.py -- --spec examples/hello_motion.json \
  --batch examples/render_batch.json --output /NEW/batched-scene
```

これは汎用bpyのバッチ実行ではなく、既存の宣言的CG操作の範囲。複数のrender frameもchunk_sizeで一つのFlamenco taskへまとめられる。起動回数やMCP往復を減らす候補だが、性能改善率は計測していない。即時に画面を見る短い操作と、重いbatch/render JOBを分ける。

## Other workloads: adoption guide

| Workload | Reuse / next decision |
| --- | --- |
| Kachinco export | 既存JOBを再利用。CGに書出しengineを複製しない |
| Generation / ComfyUI / 音声・音楽生成 | Controllerの既存JOB・provider execution IDを維持。今回置換しない |
| 大量のGlyph / Kinetai描画 | 長い処理のowner側で同じ受付・照合・結果規則を検討。短いpreviewは即時 |
| 大量画像処理・解析・ZIP準備 | 実測で長い処理を選び、owner側にJOB化。共通scheduler新設は先行しない |

お手本として共通にするのは**振る舞い**。受付前の検証、永続ID、idempotency、実行者の寿命、unknown outcome、限定cancel、適切なpoll、結果hash、保持期限、所有権を各ownerで満たす。再利用する相手と境界が実例で揃うまでは、全アプリ共通の汎用基盤へ昇格させない。

## Recovery / limits

- Work/Blender MCP切断: 次の接続で同じhost configとjob_idを使う。CGにrenderプロセスがないので描画はFlamencoで続く。
- CG呼出元再起動: SQLiteと共有ファイルを再利用。backend IDまたはmetadataで照合。
- Manager再起動/停止: backend実装の復旧に任せ、CGはunavailableとして以前の状態を保持。Managerの実停止・再起動は受入試験で勝手に実行しない。
- Worker再起動: 再割当・プロセス管理はFlamenco。CGから手動PID操作しない。
- 受付不明0件/複数件: 自動再投入しない。operatorがManagerの履歴・ログを確認する。
- このJOB基盤単体ではpoll間隔を尊重して後から再取得する。[別途のMCP Events実験](job-events.md)は、2026年11月3日にLIMEの実トンネル・ChatGPTの実購読を使い、1フレームの成功JOBから会話への報告まで受入れ済み。スマホ/OSバナー、実service再起動中の配信、複数ownerなどの未受入れ範囲は[通知受入れ記録](job-events-acceptance.md)を参照。
- result収集は最大byteとログ件数を制限した同期処理。大規模ZIP作成が長くなる場合は、そのownerで別JOBへ切り出す次の候補。

See [acceptance evidence](render-jobs-acceptance.md) for actual tests and rendering; unit tests alone are not Blender acceptance.
