import Foundation

/// AIエージェントが実行するアクション
enum AgentAction: Identifiable {
    case tap(position: CGPoint)
    case drag(from: CGPoint, to: CGPoint)
    case swipe(from: CGPoint, to: CGPoint, duration: TimeInterval)
    case playCard(card: Card, position: CGPoint)
    case wait(duration: TimeInterval)
    case none(reason: String)

    var id: String {
        switch self {
        case .tap(let pos): return "tap_\(pos.x)_\(pos.y)"
        case .drag(let from, let to): return "drag_\(from.x)_\(to.x)"
        case .swipe(let from, _, _): return "swipe_\(from.x)_\(from.y)"
        case .playCard(let card, _): return "play_\(card.id)"
        case .wait(let d): return "wait_\(d)"
        case .none(let r): return "none_\(r)"
        }
    }

    var description: String {
        switch self {
        case .tap(let pos):
            return "タップ (\(f(pos.x)), \(f(pos.y)))"
        case .drag(let from, let to):
            return "ドラッグ (\(f(from.x)),\(f(from.y))) → (\(f(to.x)),\(f(to.y)))"
        case .swipe(let from, let to, _):
            return "スワイプ (\(f(from.x)),\(f(from.y))) → (\(f(to.x)),\(f(to.y)))"
        case .playCard(let card, let pos):
            return "カード配置: \(card.name) → (\(f(pos.x)), \(f(pos.y)))"
        case .wait(let duration):
            return "待機 \(String(format: "%.1f", duration))秒"
        case .none(let reason):
            return "アクションなし: \(reason)"
        }
    }

    private func f(_ v: CGFloat) -> String {
        String(format: "%.2f", v)
    }
}

/// エージェントの判断理由を含むアクション決定
struct AgentDecision {
    let action: AgentAction
    let reasoning: String
    let confidence: Double  // 0.0 - 1.0
    let timestamp: Date

    init(action: AgentAction, reasoning: String, confidence: Double) {
        self.action = action
        self.reasoning = reasoning
        self.confidence = confidence
        self.timestamp = Date()
    }
}

/// エージェントのログエントリ
struct AgentLogEntry: Identifiable {
    let id = UUID()
    let timestamp: Date
    let level: LogLevel
    let message: String
    let screenshot: Data?

    enum LogLevel: String {
        case info = "INFO"
        case action = "ACTION"
        case warning = "WARN"
        case error = "ERROR"
        case thinking = "THINK"
    }

    init(level: LogLevel, message: String, screenshot: Data? = nil) {
        self.timestamp = Date()
        self.level = level
        self.message = message
        self.screenshot = screenshot
    }
}
