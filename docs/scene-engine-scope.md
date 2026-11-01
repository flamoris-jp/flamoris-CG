# 旧Scene Engine計画とCG・Cinemaの責任整理

**整理日: 2026-11-01。** 対象: [Kachinco #124](https://github.com/flamoris-jp/flamoris-kachinco/issues/124)、[Glyph #3](https://github.com/flamoris-jp/flamoris-glyph/issues/3)。制作側の研究バックログ: [CG #8](https://github.com/flamoris-jp/flamoris-CG/issues/8)。

既存方針に基づく責任・依存関係の整理であり、旧計画の全面廃止、独立Scene Engineリポジトリ新設、Cinema再開、実装着手を決定するものではない。両Issueは元の本文を履歴として残し、openで後続判断を追跡する。

## 根拠と現在地

- CGの [README](../README.md)、[architecture](architecture.md)、[roadmap](roadmap.md): 単一シーン/素材クリップのオブジェクト・動作・時間・描画依頼を扱う。現在はBlender実験基盤。
- Cinemaの [構想と休眠](https://github.com/flamoris-jp/flamoris-cinema/blob/main/docs/vision-and-pause.md): 2026-10-31から開発休眠。将来の作品全体の意図・出来事・ツール選択・制作計画という構想と、停止前のScene/Take実験を区別する。
- [CinemaのGlyph adapter](https://github.com/flamoris-jp/flamoris-cinema/blob/main/docs/glyph-actors.md)にはread-only形状取込の実装・受入証跡がある。全くの未着手として作り直さず、先に比較する。ただしCGへの移植・互換性・再受入れは未実施。

CGで受入済みなのはLinux headlessの静止プレビュー・保存・MCP画像取得の範囲。物理、Glyph取込、動画encode、自動handoffは未実装。PNG連番出力コードの存在も、連番の実機受入れを意味しない。

## 責任の境界

| 担当 | 所有するもの | 境界・現状 |
| --- | --- | --- |
| Glyph | 輪郭、Style DNA、occurrence/variant/stroke ID、出典、immutable bundleと検証 | 物理・CGの時間・編集タイムラインを持たない。形状契約はGlyph #3 |
| CG | クリップ内のオブジェクト参照、配置/単位変換、動作、時間、シーン、カメラ/照明設定と描画依頼、出力付随データ | 素材クリップの制作側。高度な機能は研究段階 |
| Blender | ネイティブ形状・物理・マテリアル・描画の実行 | CGが必要な機能を限定的に利用 |
| KineticTypo | 文字演出・配置・動作と編集可能な文字composition | CGの物体シミュレーションを取り込む前提は置かない |
| Kachinco | 素材登録、配置、編集、音、合成、最終出力、project/history | CGの出力を既存の正規interface経由で受け取る |
| Generation | 生成アセットとモデル推論 | 物理状態や編集projectの正本にしない |
| Cinema（休眠） | 将来の作品全体の意図、出来事、ツール間計画、制作履歴 | CGの必須依存ではない。旧所有権表は当時の実装の説明 |

## 旧計画の扱い

「CGへ整理」は責任とバックログの移管であり、コード・資産の移動や機能完成を意味しない。

| #124の内容 | 分類 | 現在の扱い |
| --- | --- | --- |
| assets/actors、配置、動作、時間、シーン、カメラ・照明・描画依頼 | CGへ整理 | 単一クリップの範囲。既存lab形式から必要性で拡張 |
| Glyph SVG/bundleをread-only actorにする | CGへ整理 | Glyph #3で形状側、CG #8で消費側。Cinema adapterを比較してから再利用・再受入れを判断 |
| 重力・床との接触・反発 | CGへ整理（未実装の実験候補） | Blenderで小さく検証。摩擦・衝突イベント等を全て初回必須にはしない |
| RGBA/動画・PNG連番、fps/尺/出典/実行版等 | CGへ整理（未実装部分あり） | 出力・alpha方式を編集側と確認。自動handoffの完成は主張しない |
| Kachincoへのimport・shot timing・編集 | Kachincoに残す | #124を受け取り側の追跡に絞る。内部project直接書換え禁止 |
| 固定刻みsolver、Windows/Linuxの安定軌跡と許容差、2D collider fallback | 将来研究 | 決定性の範囲は測定して定義。現CGの保証ではない |
| 保存した演技を再計算せず別視点から再描画 | 将来研究 | Cinemaの既存証跡は参照資料。CGでは未受入れ |
| 歩行→つまずき→転倒→回復、Glyph衝突proxy | 将来研究 | 演技・キーフレーム駆動と剛体物理を分ける |
| 独立renderer、軽量モデリング/物理、ライブラリ・license比較 | 将来研究 | 自作・共有抽出・既存backendの選択は未決定 |
| AI authoring | 範囲を分割 | クリップ内の動作提案はCG研究。作品全体の計画・ツール統括はCinemaの休眠構想 |
| 「新しい別リポジトリを作る」 | 現在の必須前提から外す | CGとの重複を避け、将来抽出は実例に基づき別判断 |
| 全体共通scene schema確定→adapter→統合という固定順 | 現在不要な依存 | 必要な二者間契約だけを合意。Glyph全体を停止させない |
| 独立solver/renderer選定、5秒720p複合デモの初回必須化 | 現在の必須条件から外す | 旧受入目標は履歴保存し、CG roadmapの小さなgateごとに評価 |

入力検証、外部コード/remote asset/path escapeの拒否、資源制限、出典/版の記録、Windows/Linuxの可搬性は維持する品質条件。

## 依存関係

1. **Glyph本体は独立:** schema-2 bundle生成・検証はCGやCinemaを待たない。#3のorigin/anchor、viewBox、穴/塗り、stroke/occurrence ID、checksum、licenseは既存契約から整理できる。
2. **CGのGlyph取込だけが二者合意に依存:** 軸・単位・pivot・厚み・部品対応・対応subset・拒否条件をGlyph #3とCG #8で定める。collision proxyは派生データとして別研究にする。
3. **Kachinco受け渡しは実出力に依存:** CG #8でmediaと付随情報を検証し、#124でcodec/alpha、fps/尺、正規時間変換、素材登録・非破壊importを確認する。対応済みメディアの手動importに新scene schemaは不要。全物理/Glyph gateの完了も必須にしない。
4. **Cinemaを必須依存にしない:** 将来の上位project形式、全ツール共通schema、Cinema再開を着手条件にしない。

CG lab JSONはBlender Z-up・1-based frameの実験形式で、Cinema Scene/Takeとは別物。GlyphのY-down 1000×1000座標やKachincoの35,280,000 ticks/secondへ暗黙に読み替えない。adapterで変換を明示・検証する。統一スキーマはこの整理で作らない。

## 履歴と次の判断

元Issueの目標・受入条件は作成時の計画として保存し、未チェック項目の完了や全面廃止を宣言しない。Cinemaのコード・契約・実機証跡も元リポジトリに保持する。[cinema-reuse](cinema-reuse.md)に沿って必要な機能単位で比較し、CGで再受入れする。

実装に進む場合は、具体的な制作例と対象gateを選ぶ。独立エンジン、共通基盤抽出、Cinema再開はそれぞれ別の明示的な判断を要する。この文書はそれらを起動しない。
