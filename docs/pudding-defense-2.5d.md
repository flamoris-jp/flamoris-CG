# 2.5D experiment: プリン防衛戦

Related: [CG #10](https://github.com/flamoris-jp/flamoris-CG/issues/10).

制作で不足した機能を一つずつ足す実験。**背景は編集可能なBlender 3D、キャラクターは固定方向の透過2D**。奥行き・遮蔽・カメラを利用する。今回の15秒は動作と画面構成を確かめるラフであり、骨格歩行、手による小道具操作、表情差分、口パク、音声は未実装。

## Reusable additions

- `primitive: "sprite"` と `asset` ID。JSONにファイルパスやURLは置かない。
- `--assets DIRECTORY` で明示指定したディレクトリの `<id>.png` のみ解決。ID、実パスの包含、ファイルサイズ16 MiB、ヘッダー寸法4096×4096以内・総画素8,388,608以下を検査。PNG本体のデコードはBlenderが行う。
- スプライトは底辺中央を原点とするX/Z平面、正面は-Y。`scale.x/z` が幅/高さで、画像の縦横比は呼出側が合わせる。自動ビルボードや3Dキャラクターではない。
- EmissionとTransparentを画像のalphaで混合。既存`color`をRGB乗算として適用し、画像を照明で二重に陰影付けしない。キャラクターの物理的な影は作らない。
- カメラに `projection: "orthographic"` と任意の `ortho_scale`（既定8）を追加。省略時は従来のperspective。scaleはorthographic時のみ有効。
- `.blend`に画像をpackし、外部素材への参照切れを防ぐ。

```sh
python tools/validate_scene.py examples/sprite_stage.json
blender -b --threads 2 --python-exit-code 1 --python blender/build_scene.py -- \
  --spec examples/sprite_stage.json --assets /path/to/author-assets \
  --output /path/to/NEW/sprite-stage --preview

blender -b --threads 2 --python-exit-code 1 --python examples/pudding_defense.py -- \
  --assets /path/to/author-assets --output /path/to/NEW/pudding-defense

# 15秒・12fps・180枚。CPU描画には時間と容量が必要。
blender -b --threads 2 --python-exit-code 1 --python examples/pudding_defense.py -- \
  --assets /path/to/author-assets --output /path/to/NEW/pudding-sequence \
  --width 768 --samples 2 --sequence
```

`pudding_defense.py`は信頼済みのリポジトリ内に置いた固定演技の実験用スクリプト。部屋と3つのカメラ構図を持つ単体クリップであり、JSONから任意Pythonを実行する入口や、Cinemaの作品全体プランナーは追加していない。新規sceneを作り、既存sceneは削除しない。CLI汎用builderは従来どおりバックグラウンド専用のfactory sceneを使用する。

## Artwork and provenance

素材は作者が別途用意する `akino.png` / `misaki.png` / `chipsy.png`。リポジトリには人物画像、設定画、モデル、外部フォントを同梱しない。

2026-11-03の試作では愛乃が提供した3枚の設定画を参照し、内蔵画像生成で正面の3体を透過atlasとして準備した。元画像のピクセル完全切り出しではなく、同一デザインを目指した生成素材。atlasを各人物の矩形へ切り分け、描画用に縮小。実行receiptは使用PNGのSHA-256を保持する。この試作素材について、未知の第三者へ権利を許諾するものではない。

背景とプリンは本スクリプトのプリミティブから生成。看板はBlender内蔵Bfont。商用素材集・外部モデル・他リポジトリの描画コードは導入しない。

## Cinema bridge comparison

停止中のCinema READMEとBlender bridgeの記述を比較した。既存subsetはsphere/floor、平面RGB、perspective cameraを中心とし、画像alpha spriteの取り込みを提供していない。今回はCG自身のbounded contractへカメラ・asset規則を追加する範囲に収まるため、Cinema契約やimport/exportをコピーせず、小さなPNG面adapterを追加した。Cinemaの開発は再開しない。

## Initial observations and limitations

- 全身絵でも3Dの机が手前を隠し、同じ背景で寄りと引きの画面が作れた。
- 正面の絵なので、カメラを大きく周回すると薄い面であることが見える。今回のcameraは-Y側に限定。
- 移動は位置・小さな傾き・上下動。足は交互に踏み出さず、手もプリンをつかまない。Chipsyの逃走ではプリンを頭上に運ぶ演出。
- 光の影響を受けない絵と3D背景では陰影の違いが残る。アート調整・接地影は今後の検証対象。
- 見た目は画像で確認する。PythonテストだけでBlender実機の成功とは扱わない。
- Final editing / captions / audio / encoding belongs to the production workflow or Kachinco, not the reusable sprite adapter.

## Acceptance record (2026-11-03)

13 portable Python tests passed, including existing v1 compatibility, asset-ID path rejection, symlink containment, PNG bounds and camera numeric limits. Both JSON examples validate.

Blender 5.2.3 LTS, Cycles CPU, two render threads: the generic `sprite_stage.json` builder produced its packed native scene and actual 768×432 preview. The authored clip produced native `.blend`, 960×540 stills at frames 1/78/126 and a clean background. The three actual images were retrieved and inspected for alpha, occlusion, framing and plate movement. Sequence acceptance is recorded separately when all frames finish; these stills alone do not certify a completed animation.
