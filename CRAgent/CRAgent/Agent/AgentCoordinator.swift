import Foundation
import UIKit
import Combine

/// AIエージェントのメインコーディネーター
/// 観察(Observe) → 思考(Think) → 行動(Act) のループを管理
@MainActor
final class AgentCoordinator: ObservableObject {

    // MARK: - Published プロパティ

    @Published var isRunning = false
    @Published var currentGameState = GameState()
    @Published var lastDecision: AgentDecision?
    @Published var logs: [AgentLogEntry] = []
    @Published var stats = AgentStats()
    @Published var mode: AgentMode = .aiAssisted

    // MARK: - 依存関係

    private let screenCapture: ScreenCaptureService
    private let actionExecutor: ActionExecutor
    private let gameAnalyzer: CRGameAnalyzer
    private var claudeClient: ClaudeAPIClient?

    // MARK: - 設定

    private var loopInterval: TimeInterval = 1.5  // メインループ間隔（秒）
    private var useClaudeAPI = true
    private var confidenceThreshold: Double = 0.3
    private var agentTask: Task<Void, Never>?

    // MARK: - エージェントモード

    enum AgentMode: String, CaseIterable {
        case aiAssisted = "AI支援"       // Claude APIで画面分析 + AI判断
        case localOnly = "ローカル"       // ローカルロジックのみ
        case observeOnly = "観察のみ"     // 画面分析のみ（操作なし）
    }

    // MARK: - 統計

    struct AgentStats {
        var totalActions: Int = 0
        var successfulActions: Int = 0
        var apiCalls: Int = 0
        var averageResponseTime: TimeInterval = 0
        var sessionStartTime: Date?
        var cardsPlayed: Int = 0

        var sessionDuration: TimeInterval {
            guard let start = sessionStartTime else { return 0 }
            return Date().timeIntervalSince(start)
        }
    }

    // MARK: - 初期化

    init() {
        self.screenCapture = ScreenCaptureService(captureInterval: 1.0)
        self.actionExecutor = ActionExecutor()
        self.gameAnalyzer = CRGameAnalyzer()
    }

    /// Claude APIキーを設定
    func configureAPI(apiKey: String, model: String = "claude-sonnet-4-6") {
        self.claudeClient = ClaudeAPIClient(apiKey: apiKey, model: model)
        addLog(.info, "Claude API設定完了（モデル: \(model)）")
    }

    // MARK: - エージェント制御

    /// エージェントのメインループを開始
    func start() {
        guard !isRunning else { return }

        isRunning = true
        stats.sessionStartTime = Date()
        screenCapture.startCapturing()
        addLog(.info, "🎮 エージェント起動 - モード: \(mode.rawValue)")

        agentTask = Task {
            await runMainLoop()
        }
    }

    /// エージェントを停止
    func stop() {
        isRunning = false
        agentTask?.cancel()
        agentTask = nil
        screenCapture.stopCapturing()
        addLog(.info, "⏹ エージェント停止 - 合計アクション: \(stats.totalActions)")
    }

    // MARK: - メインループ

    private func runMainLoop() async {
        while isRunning && !Task.isCancelled {
            let loopStart = Date()

            do {
                // Step 1: 観察 (Observe)
                let screenshot = try await observe()

                // Step 2: 思考 (Think)
                let decision = try await think(screenshot: screenshot)

                // Step 3: 行動 (Act)
                if mode != .observeOnly {
                    try await act(decision: decision)
                }

            } catch is CancellationError {
                break
            } catch {
                addLog(.error, "ループエラー: \(error.localizedDescription)")
            }

            // ループ間隔を維持
            let elapsed = Date().timeIntervalSince(loopStart)
            let sleepTime = max(loopInterval - elapsed, 0.1)
            try? await Task.sleep(nanoseconds: UInt64(sleepTime * 1_000_000_000))
        }
    }

    // MARK: - 観察フェーズ

    private func observe() async throws -> UIImage {
        await screenCapture.captureScreen()

        guard let screenshot = screenCapture.latestScreenshot else {
            throw CRAgentError.screenCaptureNotAvailable
        }

        // API送信用にリサイズ
        return ScreenCaptureService.resizeForAPI(screenshot)
    }

    // MARK: - 思考フェーズ

    private func think(screenshot: UIImage) async throws -> AgentDecision {
        let startTime = Date()

        if mode == .aiAssisted, let client = claudeClient, useClaudeAPI {
            // Claude APIで分析
            do {
                let decision = try await thinkWithClaude(screenshot: screenshot, client: client)
                updateResponseTime(Date().timeIntervalSince(startTime))
                stats.apiCalls += 1
                return decision
            } catch {
                addLog(.warning, "Claude API失敗 → ローカルロジックにフォールバック: \(error.localizedDescription)")
            }
        }

        // ローカルロジックで判断
        return thinkLocally()
    }

    /// Claude APIを使った思考
    private func thinkWithClaude(screenshot: UIImage, client: ClaudeAPIClient) async throws -> AgentDecision {
        // ゲーム状態を分析
        let analysisResponse = try await client.analyzeGameState(screenshot: screenshot)
        let newState = ScreenAnalyzer.convertToGameState(from: analysisResponse)
        currentGameState = newState

        if let summary = analysisResponse.situationSummary {
            addLog(.thinking, summary)
        }

        // アクション決定
        let actionResponse = try await client.decideAction(screenshot: screenshot, gameState: newState)
        let decision = ScreenAnalyzer.convertToDecision(from: actionResponse, handCards: newState.handCards)

        lastDecision = decision
        addLog(.thinking, "判断: \(decision.reasoning) (確信度: \(String(format: "%.0f%%", decision.confidence * 100)))")

        return decision
    }

    /// ローカルロジックでの思考
    private func thinkLocally() -> AgentDecision {
        let decision = gameAnalyzer.decideAction(state: currentGameState)
        lastDecision = decision
        addLog(.thinking, "[ローカル] \(decision.reasoning)")
        return decision
    }

    // MARK: - 行動フェーズ

    private func act(decision: AgentDecision) async throws {
        // 確信度がしきい値を下回る場合はスキップ
        guard decision.confidence >= confidenceThreshold else {
            addLog(.info, "確信度が低いためスキップ (\(String(format: "%.0f%%", decision.confidence * 100)))")
            return
        }

        // アクション実行
        do {
            try await actionExecutor.execute(decision.action)
            stats.totalActions += 1
            stats.successfulActions += 1

            if case .playCard(let card, _) = decision.action {
                stats.cardsPlayed += 1
                addLog(.action, "✅ \(card.name) を配置")
            } else {
                addLog(.action, "✅ \(decision.action.description)")
            }
        } catch {
            stats.totalActions += 1
            addLog(.error, "❌ アクション失敗: \(error.localizedDescription)")
            throw error
        }
    }

    // MARK: - ヘルパー

    private func addLog(_ level: AgentLogEntry.LogLevel, _ message: String) {
        let entry = AgentLogEntry(level: level, message: message)
        logs.insert(entry, at: 0)

        // ログ上限
        if logs.count > 200 {
            logs = Array(logs.prefix(200))
        }
    }

    private func updateResponseTime(_ time: TimeInterval) {
        let count = Double(stats.apiCalls)
        stats.averageResponseTime = (stats.averageResponseTime * count + time) / (count + 1)
    }

    // MARK: - 設定変更

    func setLoopInterval(_ interval: TimeInterval) {
        loopInterval = max(0.5, interval)
    }

    func setConfidenceThreshold(_ threshold: Double) {
        confidenceThreshold = max(0.0, min(1.0, threshold))
    }

    func clearLogs() {
        logs.removeAll()
    }
}
