# FLAMORIS-CG

**Script-driven object animation and CG clip production for FLAMORIS.**

**Status: early Blender laboratory / 実験基盤。** まだ軽量CGエンジンではありません。Blender 5.2.3 LTSのLinux headlessで静止プレビュー生成とMCP画像取得を実機確認済みです（[範囲と証跡](docs/preview-acceptance.md)）。

FLAMORIS-CGは、**スクリプトでオブジェクトを作り、動かし、CGクリップとして出力する**制作ツールを目指します。文字を動かすKineticTypoと同じ階層で、オブジェクトを扱うことに集中します。

もうひとつの研究目的は、**AIを最初から前提にしたとき、CGツールそのものがどのように進化するかを検証すること**。従来型のツールをAIから操作できるようにするだけでなく、AIと人間が形状・動作・編集履歴を共有できる設計を実験する。結論は最初から決めない。詳しくは [AI-native CGの研究方針](docs/ai-native-research.md)。

> **最終的な目標:** 軽量なモデリング、物理演算、レンダリングを組み合わせて、必要なCGクリップを自律的に生成できる仕組み。
> **最初の手段:** 自分たちでCGソフト全部を作らず、Blenderの機能を必要な分だけ使って研究する。
> **研究テーマ:** AIにCGツールを使わせるだけでなく、AIを前提にするとCG制作の操作・設計・編集がどう変わるのかを比較実験する。

## 何者か・何を持つか

- **CGの責任:** オブジェクトの定義と参照、動作スクリプト、時間、シーン構築、描画依頼、生成したクリップと付随データ。
- **今の実装:** 単純なJSON実験仕様の検証、Blender向けのプリミティブ・キーフレーム・カメラ・照明設定、および静止プレビュー / PNG連番 / ネイティブ .blend 出力の実験用スクリプト。Captureの共通画像処理とMcp.Coreを利用する保存済みプレビュー取得アダプター。
- **限定的な受け渡し:** 明示した1件の完成JOBのZIPを検証し、MP4化して新規のKachincoテストプロジェクトへ正規CLI importで登録する[オフライン操作](docs/kachinco-handoff.md)。コードテスト・実FFmpeg fixture検証に加え、2026年11月4日にLIMEの実JOBから素材登録・保存・再読込まで実機受入れ済み。タイムライン配置・字幕・プレビュー・最終書き出し・Windows再読込・live Undo/Redoは今回の受入れ範囲外。
- **未実装:** 本格的なモデリング、衝突・剛体物理、Glyphモーフィング実行、汎用スクリプト言語、独立レンダラー、JOB完了時の自動取込、既存の本番プロジェクトへの受け渡し。コードは用意されていても実機受入れは別途必要。
- **Cinemaとの区別:** [flamoris-cinema](https://github.com/flamoris-jp/flamoris-cinema) は将来の**作品全体の演出・プロジェクト統括**（現在休眠）。CGは単体で「素材クリップを作る」。Cinemaの開発は再開しない。
- **KineticTypoとの区別:** KineticTypoは文字の動作と字幕演出。CGは物体・形状・空間の動作。共通化は実例ができてから。
- **Blenderとの区別:** Blenderが本物のモデル、物理、マテリアル、レンダリングの実行主体。CGはその操作を限定的な宣言的スクリプトへ変換する。Blender全体の複製ではない。
- **Kachincoとの区別:** Kachincoがクリップの配置・編集・音・最終書き出しを所有する。CGはKachincoの内部プロジェクトを直接書き換えない。

詳しい構成は [architecture](docs/architecture.md)、段階的な試験は [roadmap](docs/roadmap.md)、Cinema実験からの引き継ぎ判断は [cinema-reuse](docs/cinema-reuse.md) を参照。

**発想の原点:** [CG誕生の会話ログ：ちゃぶ台博物館](docs/research-notes/2026-10-31-flamoris-cg-origin-thread.md) に、GlyphのモーフィングからCG・AI-native研究・SVGの描画方式まで発展した会話の編集版を記録しています。原文引用と要約を区別し、仕様や実装の保証とは扱いません。

## 最初の実験: 球を動かす（Blender lab v0）

**非同期描画JOB:** [再接続できる描画JOB](docs/render-jobs.md) は、既設Flamencoへの投入・永続ID・再送防止・確認間隔・限定キャンセル・結果ZIPを扱います。CLIと既設Blender MCPから呼ぶデータAPIを共有し、CG自身は描画子プロセスを起動しません。[実機受入れ](docs/render-jobs-acceptance.md)を参照。

**完了通知の追加実験:** [MCP Events](docs/job-events.md) は、既存Blender操作を引き継ぐ単一owner用HTTP入口と、描画JOB単位の完了・失敗・取消通知を扱います。2026年11月3日、LIMEの実トンネル経由で1フレームの成功JOBを通知し、ChatGPTの実購読・署名callback・正本状態の再確認・会話への成功報告まで[実機受入れ](docs/job-events-acceptance.md)済みです。スマホ/OSバナー、実service再起動中の配信、複数ownerなどは未受入れです。

**操作バッチ:** `--batch examples/render_batch.json` で位置・色・描画設定等を一括検証してから一度のBlender構築へ渡せます。不正な操作は開始前に拒否し、任意Pythonは実行しません。

**2.5Dの追加実験:** [プリン防衛戦](docs/pudding-defense-2.5d.md) では、3D背景に透過PNGのキャラクターを置き、平行投影でアニメ風の単体クリップを試します。`examples/sprite_stage.json` と `examples/pudding_defense.py` が入口です。全身スプライトの移動を扱うラフで、骨格歩行・表情・口パクはまだありません。

**2D × CGのアニメーション研究（2026-11-05）:** [研究結果のまとめ](docs/research-notes/2026-11-05-two-pose-hybrid-animation.md)に、2枚の原画の画素変形・外周線・部位別変形から、原画を使う2D片腕とBlenderの手の回転までを記録しました。[2D片腕](experiments/two_pose/README.md)は48フレーム・720×900・24fps、[原画に合わせたBlenderの手](experiments/blender_hand_turn/SOURCE_FIT.md)は32フレーム・800×600・24fpsの透過連番を作成。後者は原画の甲・掌に手動設計の厚みを付けた2.5Dモデルです。新しい手と2Dの腕の接続、自動分解、隠れ面の自動復元、解剖学的な回転推定は未実装。既存シーン/JOB APIの機能追加ではなく、入力を限定した研究用スクリプトです。

実験用スクリプトの [hello_motion.json](examples/hello_motion.json) は、床と球を作り、球の位置をいくつかのキーフレームで変更します。**物理演算ではなく、指定した動きの再生**です。任意のPythonコードをJSONから実行しません。

事前条件: Python 3.11+、Blender（別途インストール、実行可能な `blender` コマンド）、描画する場合は利用できるCPU環境。CIはPython仕様検証とWindows/Linuxの画像・MCP境界テストを行います。Blender実機試験は[別記録](docs/preview-acceptance.md)です。

```sh
# Blenderなしでも入力の検証ができる
python tools/validate_scene.py examples/hello_motion.json
python -m unittest discover -s tests -v

# Blenderでシーンを作成し、.blendのみ保存
blender -b --python-exit-code 1 --python blender/build_scene.py -- --spec examples/hello_motion.json --output outputs/hello

# 新しい出力フォルダーにPNGプレビューも作る（同じパスを再使用しない）
blender -b --python-exit-code 1 --python blender/build_scene.py -- --spec examples/hello_motion.json --output outputs/hello-preview --preview

# 全フレームをPNG連番で描く（処理時間と容量に注意）
blender -b --python-exit-code 1 --python blender/build_scene.py -- --spec examples/hello_motion.json --output outputs/hello-frames --sequence
```

作成するフォルダーが既存なら安全のため失敗します。対応するオブジェクトは `cube`・`uv_sphere`・明示したPNG素材を使う `sprite` に限定し、FPS、尺、数値範囲、キーフレーム数を制限します。Blenderがインストールされていなくても入力スキーマのユニットテストはできます。汎用builderはMP4をエンコードしません。完成JOBの連続PNGを映像化する別操作は[受け渡しCLI](docs/kachinco-handoff.md)を参照。最終編集・音・書き出しはKachincoの範囲です。

## 目標と進め方

1. **現在:** Blender実験場。オブジェクトの生成・移動・視点・描画を一つずつ観察する。
2. **次:** Blender剛体物理・簡単な形状操作・書き出しの検証。必要な機能を絞る。
3. **次:** スクリプトからCGクリップまでの安定した入口を作る。Kachincoへの素材登録は限定受入れ済み。次段階の配置・編集・書き出しは個別に検証する。
4. **長期:** Blender依存のまま残す部分と、小さく自作・差し替えできるモデル/物理/レンダラーを切り分ける。

既存のCinema実験にはBlender 5.2.3のCPU/HIP描画、Glyph形状、複数視点、Flamenco、Kachinco受け渡しの証跡がありますが、**この新リポジトリで再検証済みとはみなしません**。移植や依存追加は個別の必要性を確認してから。

## 方針

- Windows / Linuxの両方で扱えるデータ・コードを優先し、ローカルの専用パス、GPU名、サーバー構成を固定しない。
- 入力データは宣言的・検証可能にし、外部入力から任意のPython、Blender操作、ネットワーク呼出を許さない。
- モデル・映像・生成物・大容量データは既定でコミットしない。クリップ出力は新規フォルダーへ。
- Blenderの動作・物理・レンダリングの実機試験結果は、コードの存在やPython CIとは区別する。
- 最初からCinema、Kachinco、Glyphの所有する機能や既存の実装を複製しない。

Start from the [FLAMORIS organization map](https://github.com/flamoris-jp/.github).

## License

Code: [Apache License 2.0](LICENSE). Blender、フォント、モデル、素材等のサードパーティー資産は各自のライセンスに従います。


## AIと一緒にプレビューを見る

保存済みプレビューを `preview.get` で実画像として取得できます。[構成・ビルド・利用](docs/preview-mcp.md)を参照。生成と取得は別操作で、読み取りではレンダリングしません。

## 旧Scene Engine計画との関係

Kachinco #124 / Glyph #3の旧計画は、[責任・依存関係の整理](docs/scene-engine-scope.md)と[CG #8](https://github.com/flamoris-jp/flamoris-CG/issues/8)で追跡します。クリップ内のオブジェクト・動作・シーン・出力をCGの範囲へ整理し、Glyphは形状、Kachincoは編集を保持します。独立エンジン新設、共通schema先行確定、Cinema再開は既定事項にしません。バックログの整理で、機能実装・実機受入れの追加ではありません。


