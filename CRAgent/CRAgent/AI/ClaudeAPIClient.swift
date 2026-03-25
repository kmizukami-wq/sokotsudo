import Foundation
import UIKit

/// Claude Vision APIクライアント
actor ClaudeAPIClient {

    private let apiKey: String
    private let model: String
    private let baseURL = "https://api.anthropic.com/v1/messages"
    private let session: URLSession

    init(apiKey: String, model: String = "claude-sonnet-4-6") {
        self.apiKey = apiKey
        self.model = model
        self.session = URLSession(configuration: .default)
    }

    // MARK: - 画面分析

    /// スクリーンショットを分析してゲーム状態をJSON形式で返す
    func analyzeScreen(screenshot: UIImage, prompt: String) async throws -> String {
        guard let imageData = screenshot.jpegData(compressionQuality: 0.7) else {
            throw CRAgentError.imageConversionFailed
        }

        let base64Image = imageData.base64EncodedString()

        let requestBody: [String: Any] = [
            "model": model,
            "max_tokens": 2048,
            "messages": [
                [
                    "role": "user",
                    "content": [
                        [
                            "type": "image",
                            "source": [
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64Image
                            ]
                        ],
                        [
                            "type": "text",
                            "text": prompt
                        ]
                    ]
                ]
            ]
        ]

        var request = URLRequest(url: URL(string: baseURL)!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
        request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
        request.httpBody = try JSONSerialization.data(withJSONObject: requestBody)
        request.timeoutInterval = 30

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw CRAgentError.invalidResponse
        }

        guard httpResponse.statusCode == 200 else {
            let errorBody = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw CRAgentError.apiError(statusCode: httpResponse.statusCode, message: errorBody)
        }

        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        guard let content = json?["content"] as? [[String: Any]],
              let firstBlock = content.first,
              let text = firstBlock["text"] as? String else {
            throw CRAgentError.parseError("レスポンスからテキストを取得できません")
        }

        return text
    }

    /// ゲーム状態を分析するための専用プロンプトで画面を分析
    func analyzeGameState(screenshot: UIImage) async throws -> GameAnalysisResponse {
        let prompt = """
        あなたはクラッシュロワイヤルのゲーム画面を分析するAIです。
        このスクリーンショットを分析し、以下のJSON形式で正確に回答してください。

        ```json
        {
          "phase": "battle|matchmaking|overtime|victory|defeat|draw|unknown",
          "elixir": 0-10の数値,
          "hand_cards": [
            {"name": "カード名", "slot": 0-3}
          ],
          "next_card": "カード名またはnull",
          "my_towers": {
            "king_hp_percent": 0-100,
            "left_princess_hp_percent": 0-100,
            "right_princess_hp_percent": 0-100,
            "left_destroyed": true/false,
            "right_destroyed": true/false
          },
          "enemy_towers": {
            "king_hp_percent": 0-100,
            "left_princess_hp_percent": 0-100,
            "right_princess_hp_percent": 0-100,
            "left_destroyed": true/false,
            "right_destroyed": true/false
          },
          "active_units": [
            {
              "name": "ユニット名",
              "x": 0.0-1.0,
              "y": 0.0-1.0,
              "is_enemy": true/false,
              "hp_percent": 0-100
            }
          ],
          "time_remaining_seconds": 秒数,
          "is_double_elixir": true/false,
          "situation_summary": "現在の戦況の簡潔な説明"
        }
        ```

        重要:
        - 座標は画面の左上を(0,0)、右下を(1,1)とした正規化座標
        - 自分側が画面下、敵側が画面上
        - カード名は日本語で
        - 確信が持てない場合はnullを使用
        - JSONのみを返し、他の説明は不要
        """

        let responseText = try await analyzeScreen(screenshot: screenshot, prompt: prompt)
        return try parseGameAnalysis(responseText)
    }

    /// 次のアクションを決定するためのAI判断を取得
    func decideAction(screenshot: UIImage, gameState: GameState) async throws -> ActionDecisionResponse {
        let stateDescription = buildStateDescription(gameState)

        let prompt = """
        あなたはクラッシュロワイヤルの上級プレイヤーAIです。
        画面の状態と現在のゲーム情報を基に、次に取るべき最適なアクションを決定してください。

        現在のゲーム状態:
        \(stateDescription)

        以下のJSON形式で回答してください:
        ```json
        {
          "action_type": "play_card|wait|tap",
          "card_name": "カード名（play_cardの場合）",
          "target_x": 0.0-1.0,
          "target_y": 0.0-1.0,
          "reasoning": "判断理由の説明",
          "confidence": 0.0-1.0,
          "strategy": "defense|offense|counter_attack|elixir_advantage|spell_value"
        }
        ```

        戦略ガイドライン:
        - エリクサーアドバンテージを常に意識する
        - 敵ユニットが自陣に来たら防衛を優先
        - カウンター攻撃のチャンスを逃さない
        - 呪文は価値のあるタイミングで使う（複数ユニットにヒットする等）
        - エリクサーが10で溢れないようにする
        - 開幕はエリクサーが溜まるまで待つ（相手が先に出すのを待つ）
        - JSONのみを返すこと
        """

        let responseText = try await analyzeScreen(screenshot: screenshot, prompt: prompt)
        return try parseActionDecision(responseText)
    }

    // MARK: - パース

    private func parseGameAnalysis(_ text: String) throws -> GameAnalysisResponse {
        let jsonString = extractJSON(from: text)
        guard let data = jsonString.data(using: .utf8) else {
            throw CRAgentError.parseError("JSONデータへの変換に失敗")
        }
        return try JSONDecoder().decode(GameAnalysisResponse.self, from: data)
    }

    private func parseActionDecision(_ text: String) throws -> ActionDecisionResponse {
        let jsonString = extractJSON(from: text)
        guard let data = jsonString.data(using: .utf8) else {
            throw CRAgentError.parseError("JSONデータへの変換に失敗")
        }
        return try JSONDecoder().decode(ActionDecisionResponse.self, from: data)
    }

    /// レスポンスからJSON部分を抽出
    private func extractJSON(from text: String) -> String {
        // ```json ... ``` ブロックを検出
        if let jsonRange = text.range(of: "```json"),
           let endRange = text.range(of: "```", range: jsonRange.upperBound..<text.endIndex) {
            return String(text[jsonRange.upperBound..<endRange.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        // { ... } を直接検出
        if let start = text.firstIndex(of: "{"),
           let end = text.lastIndex(of: "}") {
            return String(text[start...end])
        }
        return text
    }

    private func buildStateDescription(_ state: GameState) -> String {
        var desc = "フェーズ: \(state.phase.rawValue)\n"
        desc += "エリクサー: \(state.elixir)\n"
        desc += "手札: \(state.handCards.map { "\($0.name)(\($0.elixirCost))" }.joined(separator: ", "))\n"
        desc += "自タワーHP: キング=\(state.myTowerHP.king), 左=\(state.myTowerHP.leftPrincess), 右=\(state.myTowerHP.rightPrincess)\n"
        desc += "敵タワーHP: キング=\(state.enemyTowerHP.king), 左=\(state.enemyTowerHP.leftPrincess), 右=\(state.enemyTowerHP.rightPrincess)\n"
        desc += "残り時間: \(Int(state.timeRemaining))秒\n"
        desc += "2倍エリクサー: \(state.isDoubleElixir)\n"
        desc += "防衛必要: \(state.needsDefense)\n"
        desc += "フィールドユニット数: 味方=\(state.activeUnits.filter{!$0.isEnemy}.count) 敵=\(state.activeUnits.filter{$0.isEnemy}.count)\n"
        return desc
    }
}

// MARK: - APIレスポンスモデル

struct GameAnalysisResponse: Codable {
    let phase: String
    let elixir: Double?
    let handCards: [HandCard]?
    let nextCard: String?
    let myTowers: TowerState?
    let enemyTowers: TowerState?
    let activeUnits: [DetectedUnitResponse]?
    let timeRemainingSeconds: Int?
    let isDoubleElixir: Bool?
    let situationSummary: String?

    enum CodingKeys: String, CodingKey {
        case phase, elixir
        case handCards = "hand_cards"
        case nextCard = "next_card"
        case myTowers = "my_towers"
        case enemyTowers = "enemy_towers"
        case activeUnits = "active_units"
        case timeRemainingSeconds = "time_remaining_seconds"
        case isDoubleElixir = "is_double_elixir"
        case situationSummary = "situation_summary"
    }

    struct HandCard: Codable {
        let name: String
        let slot: Int?
    }

    struct TowerState: Codable {
        let kingHpPercent: Int?
        let leftPrincessHpPercent: Int?
        let rightPrincessHpPercent: Int?
        let leftDestroyed: Bool?
        let rightDestroyed: Bool?

        enum CodingKeys: String, CodingKey {
            case kingHpPercent = "king_hp_percent"
            case leftPrincessHpPercent = "left_princess_hp_percent"
            case rightPrincessHpPercent = "right_princess_hp_percent"
            case leftDestroyed = "left_destroyed"
            case rightDestroyed = "right_destroyed"
        }
    }

    struct DetectedUnitResponse: Codable {
        let name: String
        let x: Double
        let y: Double
        let isEnemy: Bool?
        let hpPercent: Int?

        enum CodingKeys: String, CodingKey {
            case name, x, y
            case isEnemy = "is_enemy"
            case hpPercent = "hp_percent"
        }
    }
}

struct ActionDecisionResponse: Codable {
    let actionType: String
    let cardName: String?
    let targetX: Double?
    let targetY: Double?
    let reasoning: String?
    let confidence: Double?
    let strategy: String?

    enum CodingKeys: String, CodingKey {
        case actionType = "action_type"
        case cardName = "card_name"
        case targetX = "target_x"
        case targetY = "target_y"
        case reasoning, confidence, strategy
    }
}

// MARK: - エラー

enum CRAgentError: LocalizedError {
    case imageConversionFailed
    case invalidResponse
    case apiError(statusCode: Int, message: String)
    case parseError(String)
    case screenCaptureNotAvailable
    case actionExecutionFailed(String)

    var errorDescription: String? {
        switch self {
        case .imageConversionFailed: return "画像の変換に失敗しました"
        case .invalidResponse: return "無効なレスポンスです"
        case .apiError(let code, let msg): return "APIエラー (\(code)): \(msg)"
        case .parseError(let msg): return "パースエラー: \(msg)"
        case .screenCaptureNotAvailable: return "画面キャプチャが利用できません"
        case .actionExecutionFailed(let msg): return "アクション実行失敗: \(msg)"
        }
    }
}
