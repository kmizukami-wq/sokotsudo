import Foundation
import UIKit

/// クラッシュロワイヤル専用のゲーム分析・戦略エンジン
final class CRGameAnalyzer {

    // MARK: - 戦略決定

    /// ゲーム状態に基づいて最適なアクションを決定（ローカルロジック）
    /// Claude APIが遅い場合やオフライン時のフォールバック
    func decideAction(state: GameState) -> AgentDecision {
        // 1. バトル外なら何もしない
        guard state.phase == .battle || state.phase == .overtime || state.phase == .tripleElixir else {
            return AgentDecision(
                action: .none(reason: "バトル中ではありません（\(state.phase.rawValue)）"),
                reasoning: "バトルフェーズ以外ではアクションを取りません",
                confidence: 1.0
            )
        }

        // 2. 手札がなければ待機
        guard !state.handCards.isEmpty else {
            return AgentDecision(
                action: .wait(duration: 0.5),
                reasoning: "手札情報がまだ取得できていません",
                confidence: 0.5
            )
        }

        // 3. 防衛が必要な場合
        if state.needsDefense {
            return decideDefensiveAction(state: state)
        }

        // 4. エリクサーが溢れそうな場合（9以上）
        if state.elixir >= 9 {
            return decideOverflowAction(state: state)
        }

        // 5. カウンターアタックのチャンス
        if state.canCounterAttack {
            return decideCounterAttackAction(state: state)
        }

        // 6. エリクサーが十分で攻撃チャンス
        if state.elixir >= 6 && !state.isDoubleElixir {
            return decideOffensiveAction(state: state)
        }

        // 7. 2倍エリクサータイムは積極的に
        if state.isDoubleElixir && state.elixir >= 5 {
            return decideOffensiveAction(state: state)
        }

        // 8. それ以外は待機（エリクサーを貯める）
        return AgentDecision(
            action: .wait(duration: 1.0),
            reasoning: "エリクサーを貯めています（現在: \(state.elixir)）",
            confidence: 0.7
        )
    }

    // MARK: - 防衛戦略

    private func decideDefensiveAction(state: GameState) -> AgentDecision {
        let enemyUnits = state.activeUnits.filter { $0.isEnemy && $0.position.y > 0.5 }

        // 防衛に適したカードを探す
        let defenseCards = state.playableCards.sorted { a, b in
            defenseScore(card: a) > defenseScore(card: b)
        }

        guard let bestCard = defenseCards.first else {
            return AgentDecision(
                action: .wait(duration: 0.5),
                reasoning: "防衛カードを出すエリクサーが足りません",
                confidence: 0.4
            )
        }

        // 敵ユニットの位置に応じて防衛位置を決定
        let avgEnemyX = enemyUnits.map { $0.position.x }.reduce(0, +) / max(CGFloat(enemyUnits.count), 1)
        let defensePosition: CGPoint

        if avgEnemyX < 0.4 {
            defensePosition = ActionExecutor.defenseLeftPosition
        } else if avgEnemyX > 0.6 {
            defensePosition = ActionExecutor.defenseRightPosition
        } else {
            defensePosition = ActionExecutor.defenseCenterPosition
        }

        return AgentDecision(
            action: .playCard(card: bestCard, position: defensePosition),
            reasoning: "敵ユニットが自陣に接近中 → \(bestCard.name)で防衛",
            confidence: 0.8
        )
    }

    // MARK: - エリクサー溢れ防止

    private func decideOverflowAction(state: GameState) -> AgentDecision {
        // 最もコストの低いカードを出す
        let cheapestPlayable = state.playableCards.min(by: { $0.elixirCost < $1.elixirCost })

        guard let card = cheapestPlayable else {
            return AgentDecision(
                action: .wait(duration: 0.3),
                reasoning: "エリクサーが溢れそうだがカードを出せません",
                confidence: 0.3
            )
        }

        let position: CGPoint
        switch card.cardType {
        case .building:
            position = ActionExecutor.buildingCenterPosition
        case .spell:
            // 呪文は敵タワーに
            position = state.weakerEnemyTowerSide == .left
                ? ActionExecutor.attackLeftPosition
                : ActionExecutor.attackRightPosition
        case .troop:
            // ユニットは橋の後ろに
            position = state.weakerEnemyTowerSide == .left
                ? CGPoint(x: 0.3, y: 0.55)
                : CGPoint(x: 0.7, y: 0.55)
        }

        return AgentDecision(
            action: .playCard(card: card, position: position),
            reasoning: "エリクサー溢れ防止 → \(card.name)を配置（エリクサー: \(state.elixir)）",
            confidence: 0.7
        )
    }

    // MARK: - カウンターアタック

    private func decideCounterAttackAction(state: GameState) -> AgentDecision {
        // サポートユニットを追加
        let supportCards = state.playableCards.filter {
            $0.cardType == .troop && $0.elixirCost <= 5
        }.sorted { offenseScore(card: $0) > offenseScore(card: $1) }

        guard let card = supportCards.first else {
            return AgentDecision(
                action: .wait(duration: 0.5),
                reasoning: "カウンター用のサポートカードがありません",
                confidence: 0.4
            )
        }

        // 味方ユニットの近くに配置
        let friendlyUnits = state.activeUnits.filter { !$0.isEnemy && $0.position.y < 0.5 }
        let avgX = friendlyUnits.map { $0.position.x }.reduce(0, +) / max(CGFloat(friendlyUnits.count), 1)
        let position = CGPoint(x: avgX, y: 0.45)

        return AgentDecision(
            action: .playCard(card: card, position: position),
            reasoning: "カウンターアタック → \(card.name)でサポート",
            confidence: 0.75
        )
    }

    // MARK: - 攻撃戦略

    private func decideOffensiveAction(state: GameState) -> AgentDecision {
        let offenseCards = state.playableCards
            .filter { $0.cardType == .troop }
            .sorted { offenseScore(card: $0) > offenseScore(card: $1) }

        guard let card = offenseCards.first else {
            return AgentDecision(
                action: .wait(duration: 1.0),
                reasoning: "攻撃可能なユニットが手札にありません",
                confidence: 0.5
            )
        }

        let targetSide = state.weakerEnemyTowerSide
        let position: CGPoint

        // 高コストユニットは後ろから、低コストは橋前に
        if card.elixirCost >= 5 {
            position = targetSide == .left
                ? CGPoint(x: 0.3, y: 0.7)  // 自陣後方
                : CGPoint(x: 0.7, y: 0.7)
        } else {
            position = targetSide == .left
                ? ActionExecutor.bridgeLeftPosition
                : ActionExecutor.bridgeRightPosition
        }

        return AgentDecision(
            action: .playCard(card: card, position: position),
            reasoning: "攻撃 → \(card.name)を\(targetSide == .left ? "左" : "右")サイドに配置",
            confidence: 0.65
        )
    }

    // MARK: - カードスコアリング

    private func defenseScore(card: Card) -> Double {
        // 防衛向きカードほどスコアが高い
        switch card.id {
        case "valkyrie", "knight": return 9
        case "minipekka": return 8.5
        case "skeleton_army": return 8
        case "cannon", "tesla": return 8
        case "inferno_tower": return 9
        case "musketeer": return 7
        case "electro_wizard": return 8
        case "mega_knight": return 9
        case "tornado": return 7
        default:
            return card.cardType == .building ? 7 : Double(5 - card.elixirCost) + 5
        }
    }

    private func offenseScore(card: Card) -> Double {
        // 攻撃向きカードほどスコアが高い
        switch card.id {
        case "hog_rider": return 9
        case "balloon": return 9
        case "giant": return 8
        case "royal_giant": return 8
        case "golem": return 8.5
        case "pekka": return 7
        case "mega_knight": return 7
        case "lava_hound": return 8.5
        case "goblin_barrel": return 7
        default:
            return card.cardType == .troop ? 5 : 3
        }
    }
}
