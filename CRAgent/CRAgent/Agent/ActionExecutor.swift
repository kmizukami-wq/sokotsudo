import Foundation
import UIKit

/// タップ・スワイプ・ドラッグアクションを実行するエグゼキューター
/// iOS Accessibility APIとIOHIDイベントを使用
@MainActor
final class ActionExecutor: ObservableObject {

    @Published var lastExecutedAction: AgentAction?
    @Published var isExecuting = false

    /// 画面サイズ（アクション座標変換用）
    private var screenSize: CGSize {
        UIScreen.main.bounds.size
    }

    // MARK: - アクション実行

    /// AgentActionを実行
    func execute(_ action: AgentAction) async throws {
        isExecuting = true
        defer { isExecuting = false }

        lastExecutedAction = action

        switch action {
        case .tap(let position):
            try await performTap(at: position)

        case .drag(let from, let to):
            try await performDrag(from: from, to: to, duration: 0.3)

        case .swipe(let from, let to, let duration):
            try await performDrag(from: from, to: to, duration: duration)

        case .playCard(let card, let position):
            try await performCardPlay(card: card, targetPosition: position)

        case .wait(let duration):
            try await Task.sleep(nanoseconds: UInt64(duration * 1_000_000_000))

        case .none:
            break
        }
    }

    // MARK: - タッチ操作

    /// 正規化座標でタップを実行
    private func performTap(at normalizedPosition: CGPoint) async throws {
        let screenPoint = denormalize(normalizedPosition)

        // IOHIDEvent を使用したタッチシミュレーション
        // 注意: これはプライベートAPIを使用するため、App Store提出には不向き
        // 開発・研究目的での使用を想定
        simulateTouch(at: screenPoint, type: .tap)

        // タップ後の短いウェイト
        try await Task.sleep(nanoseconds: 100_000_000) // 0.1秒
    }

    /// ドラッグ操作を実行（カード配置に使用）
    private func performDrag(from: CGPoint, to: CGPoint, duration: TimeInterval) async throws {
        let fromScreen = denormalize(from)
        let toScreen = denormalize(to)

        // ドラッグをシミュレート
        let steps = max(Int(duration / 0.016), 5) // 60FPSベース
        let dx = (toScreen.x - fromScreen.x) / CGFloat(steps)
        let dy = (toScreen.y - fromScreen.y) / CGFloat(steps)

        // タッチ開始
        simulateTouch(at: fromScreen, type: .began)

        // 中間ポイントを移動
        for i in 1..<steps {
            let point = CGPoint(
                x: fromScreen.x + dx * CGFloat(i),
                y: fromScreen.y + dy * CGFloat(i)
            )
            simulateTouch(at: point, type: .moved)
            try await Task.sleep(nanoseconds: 16_000_000) // ~16ms (60fps)
        }

        // タッチ終了
        simulateTouch(at: toScreen, type: .ended)
        try await Task.sleep(nanoseconds: 50_000_000) // 0.05秒
    }

    /// カードを手札からフィールドにドラッグして配置
    private func performCardPlay(card: Card, targetPosition: CGPoint) async throws {
        // 手札のカード位置を計算（画面下部に4枚並んでいる）
        let cardSlot = findCardSlot(card)
        let cardPosition = cardSlotPosition(slot: cardSlot)

        // カードをタップ → フィールドにドラッグ
        try await performDrag(
            from: cardPosition,
            to: targetPosition,
            duration: 0.25
        )

        // 配置確認のための短いウェイト
        try await Task.sleep(nanoseconds: 200_000_000) // 0.2秒
    }

    // MARK: - タッチシミュレーション

    private enum TouchPhase {
        case began, moved, ended, tap
    }

    /// タッチイベントをシミュレート
    /// 注意: 実機でのタッチシミュレーションにはPrivate APIまたはAccessibilityの使用が必要
    private func simulateTouch(at point: CGPoint, type: TouchPhase) {
        // 方法1: UIApplication の sendEvent を使用（アプリ内のみ）
        // 方法2: IOHIDEvent を使用（要Private API / Jailbreak）
        // 方法3: Accessibility API を使用（限定的）
        // 方法4: XCUITest フレームワーク経由（テスト環境のみ）

        // ここでは通知ベースのアプローチを使用
        // 外部のAutomation Serverと連携する設計
        NotificationCenter.default.post(
            name: .agentTouchEvent,
            object: nil,
            userInfo: [
                "x": point.x,
                "y": point.y,
                "type": "\(type)",
                "timestamp": Date().timeIntervalSince1970
            ]
        )

        #if DEBUG
        print("[ActionExecutor] Touch \(type) at (\(Int(point.x)), \(Int(point.y)))")
        #endif
    }

    // MARK: - 座標変換

    /// 正規化座標(0-1)を画面ピクセル座標に変換
    private func denormalize(_ normalized: CGPoint) -> CGPoint {
        CGPoint(
            x: normalized.x * screenSize.width,
            y: normalized.y * screenSize.height
        )
    }

    /// カードスロット位置（手札の位置）
    private func cardSlotPosition(slot: Int) -> CGPoint {
        // クラロワの手札は画面下部に4枚横並び
        // 各カードの中心X座標（正規化）
        let slotPositions: [CGFloat] = [0.22, 0.39, 0.61, 0.78]
        let safeSlot = min(max(slot, 0), 3)

        return CGPoint(
            x: slotPositions[safeSlot],
            y: 0.92 // 手札のY座標
        )
    }

    /// カードが手札の何番目にあるか推定
    private func findCardSlot(_ card: Card) -> Int {
        // AgentCoordinator経由でGameStateの手札情報を使う
        // ここではデフォルト値を返す
        return 0
    }

    // MARK: - クラロワ専用座標ヘルパー

    /// 自陣の防衛位置（キングタワー前）
    static let defenseCenterPosition = CGPoint(x: 0.5, y: 0.7)

    /// 自陣の左サイド防衛位置
    static let defenseLeftPosition = CGPoint(x: 0.3, y: 0.65)

    /// 自陣の右サイド防衛位置
    static let defenseRightPosition = CGPoint(x: 0.7, y: 0.65)

    /// 敵陣の左プリンセスタワー前
    static let attackLeftPosition = CGPoint(x: 0.3, y: 0.35)

    /// 敵陣の右プリンセスタワー前
    static let attackRightPosition = CGPoint(x: 0.7, y: 0.35)

    /// 橋の左側（ユニット配置の定番位置）
    static let bridgeLeftPosition = CGPoint(x: 0.3, y: 0.48)

    /// 橋の右側
    static let bridgeRightPosition = CGPoint(x: 0.7, y: 0.48)

    /// 自陣中央（建物配置に最適）
    static let buildingCenterPosition = CGPoint(x: 0.5, y: 0.65)
}

// MARK: - Notification

extension Notification.Name {
    static let agentTouchEvent = Notification.Name("com.sokotsudo.CRAgent.touchEvent")
}
