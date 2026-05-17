# 使用ガイド

Gemini2API の Web パネルとクライアント接続方法について説明します。

## Web 管理パネル

Gemini2API は、ブラウザベースの管理パネルを提供しています。

### アクセス方法

ブラウザで以下の URL にアクセス：

```
http://localhost:5918
```

または、リモートサーバーの場合：

```
http://サーバーIP:5918
```

### ログイン

初回アクセス時、API Key の入力を求められます。

1. `.env` ファイルまたはログから API Key を確認
2. パネルに入力してログイン

> **ヒント**: API Key は `sk-` で始まる 36 文字の文字列です。

## パネル機能

### ダッシュボード

メインページには以下の情報が表示されます：

| 項目 | 説明 |
|------|------|
| 運行時間 | サービス起動からの経過時間（リアルタイム更新） |
| 二次元コード | WeChat・スポンサーシップ QR コード（クリックで拡大） |
| システム情報 | バージョン、Python、OS、メモリ、CPU、PID、実行モード |
| 設定管理 | 轮換策略、並行数制限の変更 |
| アカウント状態 | 各アカウントの健全性、最後の使用時刻 |
| 利用可能モデル | 現在使用可能な全モデル一覧 |

### アカウント管理

複数の Google アカウントを管理します。

**機能:**

- **アカウント追加**: 新しい Google アカウントの Cookie を追加
- **アカウント削除**: 不要なアカウントを削除
- **Cookie 更新**: 期限切れの Cookie を更新
- **健全性チェック**: 各アカウントの状態を確認

**操作例:**

1. 左側メニューから「アカウント管理」を選択
2. 「新規追加」ボタンをクリック
3. Cookie（PSID と PSIDTS）を入力
4. 「追加」をクリック

### Playground（テスト環境）

API リクエストをブラウザから直接テストできます。

**使用方法:**

1. 「Playground」タブを開く
2. モデルを選択
3. メッセージを入力
4. 「送信」をクリック

**例:**

```json
{
  "model": "gemini-2.5-pro",
  "messages": [
    {
      "role": "user",
      "content": "Python で Fibonacci 数列を実装してください"
    }
  ],
  "stream": false
}
```

### リアルタイムログ

API リクエストのログをリアルタイムで表示します。

**機能:**

- **方向フィルタ**: リクエスト/レスポンスを個別に表示
- **テキスト検索**: ログ内容から検索
- **ページネーション**: 1 ページ 15 件表示
- **JSON 詳細**: 各ログの詳細情報をパネルで表示
- **ログ管理**: ログの記録開始/一時停止/クリア

### 使用統計

API 使用状況の統計情報を表示します。

**表示項目:**

| 項目 | 説明 |
|------|------|
| 累計リクエスト数 | 総リクエスト数 |
| エラー率 | エラーの割合 |
| 平均レイテンシ | 平均応答時間 |
| 轮換成功率 | Cookie 更新の成功率 |

**グラフ:**

- 時系列グラフで過去 24 時間のトレンドを表示
- 粒度（1 時間/6 時間/24 時間）を選択可能

### API Key 管理

第三方の大型言語モデル API Key を一元管理します。

**対応プロバイダ:**

- OpenAI
- Anthropic（Claude）
- Google Gemini
- OpenRouter
- カスタムプロバイダ

**操作:**

1. 「API Key 管理」を開く
2. 「新規追加」をクリック
3. プロバイダを選択
4. API Key を入力
5. 「保存」をクリック

**機能:**

- Key の有効/無効を切り替え
- 複数 Key の一括インポート/エクスポート
- Key の削除

### 設定

サービスの動作パラメータをリアルタイムで変更できます。

**設定カテゴリ:**

| カテゴリ | 設定項目 |
|---------|---------|
| パフォーマンス | 並行数、再試行回数、タイムアウト |
| 限流 | 有効/無効、ウィンドウ、最大リクエスト数 |
| 健全性チェック | 有効/無効、チェック間隔 |
| アカウント管理 | 轮換策略、Cookie 更新間隔 |
| ログ | ログレベル、保持期間 |

**変更は即座に反映されます。**

### 多言語切替

右上の地球アイコンから言語を切り替えられます。

**対応言語:**

- 简体中文（簡体中国語）
- 繁體中文（繁体中国語）
- English（英語）
- 日本語
- 한국어（韓国語）

### 右上コントロールバー

| アイコン | 機能 |
|---------|------|
| 🌙/☀️ | ダークモード/ライトモード切替 |
| 🔄 | サービス再起動 |
| 🚪 | ログアウト |

## 対応モデル

Gemini2API は以下のモデルをサポートしています。

### Gemini 3 シリーズ

| モデル名 | 説明 | 最大トークン |
|---------|------|------------|
| `gemini-3-pro` | 最新の高性能モデル | 128K |
| `gemini-3-flash` | 高速・軽量モデル | 128K |
| `gemini-3-flash-thinking` | 思考モード搭載 | 128K |
| `gemini-3-pro-plus` | Pro 限定・高容量 | 256K |
| `gemini-3-flash-plus` | Pro 限定・高速版 | 256K |
| `gemini-3-flash-thinking-plus` | Pro 限定・思考モード | 256K |

### Gemini 2 シリーズ

| モデル名 | 説明 |
|---------|------|
| `gemini-2.5-pro` | 最新 Pro モデル |
| `gemini-2.5-flash` | 最新 Flash モデル |
| `gemini-2.5-flash-thinking` | 思考モード |
| `gemini-2.0-flash` | 安定版 Flash |
| `gemini-2.0-flash-thinking` | 安定版思考モード |

### Gemini 1 シリーズ

| モデル名 | 説明 |
|---------|------|
| `gemini-1.5-pro` | 旧 Pro モデル |
| `gemini-1.5-flash` | 旧 Flash モデル |

> **ヒント**: 利用可能なモデルはアカウントの権限によって異なります。無料アカウントと Gemini Advanced アカウントで異なる場合があります。

## サードパーティクライアント接続

Gemini2API は OpenAI 互換 API を提供しているため、多くのクライアントから直接接続できます。

### ChatGPT-Next-Web

1. ChatGPT-Next-Web を起動
2. 設定 → API 設定
3. API URL を入力：

```
http://サーバーIP:5918/openai/v1
```

4. API Key を入力：

```
sk-あなたのキー
```

5. 保存して使用開始

### LobeChat

1. LobeChat を起動
2. 設定 → 言語モデル
3. プロバイダを「OpenAI」に設定
4. API URL：

```
http://サーバーIP:5918/openai/v1
```

5. API Key を入力
6. モデルを選択して使用

### OpenCat

1. OpenCat を起動
2. 設定 → API 設定
3. API エンドポイント：

```
http://サーバーIP:5918/openai/v1
```

4. API Key を入力
5. 使用開始

### cURL コマンド

```bash
curl -X POST http://localhost:5918/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-あなたのキー" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [
      {"role": "user", "content": "こんにちは"}
    ]
  }'
```

### Python SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-あなたのキー",
    base_url="http://localhost:5918/openai/v1"
)

response = client.chat.completions.create(
    model="gemini-2.5-pro",
    messages=[
        {"role": "user", "content": "Python で Hello World を出力してください"}
    ]
)

print(response.choices[0].message.content)
```

### Node.js SDK

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "sk-あなたのキー",
  baseURL: "http://localhost:5918/openai/v1",
});

const message = await client.chat.completions.create({
  model: "gemini-2.5-pro",
  messages: [
    { role: "user", content: "JavaScript で Hello World を出力してください" },
  ],
});

console.log(message.choices[0].message.content);
```

## Cookie 管理

### Cookie の有効期限

Google の Cookie は定期的に期限切れになります。

- **通常**: 数時間～数日
- **データセンター IP**: 数時間
- **住宅 IP**: 数日～数週間

### Cookie の更新方法

#### 方法 1: Web パネルから更新

1. 「アカウント管理」を開く
2. 対象アカウントの「Cookie 更新」をクリック
3. 新しい PSID と PSIDTS を入力
4. 「更新」をクリック

#### 方法 2: API で更新

```bash
curl -X PUT http://localhost:5918/admin/accounts/account-0/cookies \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-あなたのキー" \
  -d '{
    "psid": "g.新しい値",
    "psidts": "sidts-新しい値"
  }'
```

#### 方法 3: 環境変数から再読み込み

```bash
curl -X POST http://localhost:5918/admin/reload-cookies \
  -H "Authorization: Bearer sk-あなたのキー"
```

### Cookie 取得の詳細

Cookie の取得方法については、[DEPLOY.md](DEPLOY.md#cookie-取得手順) を参照してください。

## 会話コンテキスト

Gemini2API は複数ターンの会話をサポートしています。

### 自動コンテキスト管理

クライアント側で `messages` 配列に会話履歴を含めると、自動的にコンテキストが保持されます。

```python
messages = [
    {"role": "user", "content": "Python とは何ですか？"},
    {"role": "assistant", "content": "Python は..."},
    {"role": "user", "content": "その特徴を教えてください"},
]

response = client.chat.completions.create(
    model="gemini-2.5-pro",
    messages=messages
)
```

### conversation_id を使用した永続化

`conversation_id` フィールドを使用すると、複数のリクエスト間でコンテキストが保持されます。

```python
# 最初のリクエスト
response1 = client.chat.completions.create(
    model="gemini-2.5-pro",
    messages=[{"role": "user", "content": "こんにちは"}],
    conversation_id="conv-123"  # 任意の ID
)

# 2 番目のリクエスト（同じ conversation_id）
response2 = client.chat.completions.create(
    model="gemini-2.5-pro",
    messages=[{"role": "user", "content": "さっきの話の続きを教えてください"}],
    conversation_id="conv-123"  # 同じ ID を使用
)
```

> **注意**: `conversation_id` は Gemini Web の内部 ID と同期されます。

## ストリーミング応答

リアルタイムで応答を受け取ることができます。

### Python での例

```python
response = client.chat.completions.create(
    model="gemini-2.5-pro",
    messages=[{"role": "user", "content": "長編小説を書いてください"}],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### cURL での例

```bash
curl -X POST http://localhost:5918/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-あなたのキー" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [{"role": "user", "content": "詩を書いてください"}],
    "stream": true
  }'
```

## 関数呼び出し（Function Calling）

モデルに特定のタスクを実行させることができます。

```python
response = client.chat.completions.create(
    model="gemini-2.5-pro",
    messages=[
        {"role": "user", "content": "東京の天気を調べてください"}
    ],
    tools=[
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "指定都市の天気を取得",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "都市名"}
                    },
                    "required": ["city"]
                }
            }
        }
    ]
)

# モデルが関数呼び出しを提案
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        print(f"関数: {tool_call.function.name}")
        print(f"引数: {tool_call.function.arguments}")
```

## トラブルシューティング

### 接続エラー

**症状**: `Connection refused`

**解決方法**:

1. サービスが起動しているか確認：

```bash
docker compose ps
```

2. ポートが正しいか確認：

```bash
curl http://localhost:5918/health
```

### 認証エラー

**症状**: `401 Unauthorized`

**解決方法**:

1. API Key が正しいか確認
2. ヘッダーが正しいか確認：

```bash
# 正しい
curl -H "Authorization: Bearer sk-xxx"

# 間違い
curl -H "Authorization: sk-xxx"
```

### モデルが見つからない

**症状**: `Model not found`

**解決方法**:

1. 利用可能なモデルを確認：

```bash
curl http://localhost:5918/openai/v1/models \
  -H "Authorization: Bearer sk-あなたのキー"
```

2. アカウントの権限を確認（Pro アカウントが必要な場合がある）

### Cookie 期限切れ

**症状**: `SNlM0e not found` または `Invalid session`

**解決方法**:

1. Cookie を更新（上記の「Cookie 管理」を参照）
2. または新しい Cookie を取得して `.env` を更新
