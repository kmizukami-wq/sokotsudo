import Foundation
import UIKit

/// APIレスポンスをGameStateモデルに変換するアナライザー
struct ScreenAnalyzer {

    /// GameAnalysisResponseをGameStateに変換
    static func convertToGameState(from response: GameAnalysisResponse) -> GameState {
        var state = GameState()

        // フェーズ
        state.phase = parsePhase(response.phase)

        // エリクサー
        state.elixir = response.elixir ?? 0

        // 手札カード
        if let handCards = response.handCards {
            state.handCards = handCards.compactMap { handCard in
                Card.find(byName: handCard.name) ?? Card(
                    id: handCard.name.lowercased().replacingOccurrences(of: " ", with: "_"),
                    name: handCard.name,
                    elixirCost: 4, // デフォルト
                    cardType: .troop
                )
            }
        }

        // 次のカード
        if let nextCardName = response.nextCard {
            state.nextCard = Card.find(byName: nextCardName)
        }

        // タワーHP
        if let myTowers = response.myTowers {
            state.myTowerHP = convertTowerHP(myTowers, maxKing: 2400, maxPrincess: 1400)
        }
        if let enemyTowers = response.enemyTowers {
            state.enemyTowerHP = convertTowerHP(enemyTowers, maxKing: 2400, maxPrincess: 1400)
        }

        // アクティブユニット
        if let units = response.activeUnits {
            state.activeUnits = units.map { unit in
                GameState.DetectedUnit(
                    name: unit.name,
                    position: CGPoint(x: unit.x, y: unit.y),
                    isEnemy: unit.isEnemy ?? false,
                    estimatedHP: unit.hpPercent.map { Double($0) / 100.0 }
                )
            }
        }

        // 時間
        state.timeRemaining = TimeInterval(response.timeRemainingSeconds ?? 180)
        state.isDoubleElixir = response.isDoubleElixir ?? false
        state.isTripleElixir = state.timeRemaining <= 60

        return state
    }

    /// ActionDecisionResponseをAgentDecisionに変換
    static func convertToDecision(from response: ActionDecisionResponse, handCards: [Card]) -> AgentDecision {
        let action: AgentAction

        switch response.actionType {
        case "play_card":
            if let cardName = response.cardName,
               let card = handCards.first(where: { $0.name == cardName }) ?? Card.find(byName: cardName) {
                let target = CGPoint(
                    x: response.targetX ?? 0.5,
                    y: response.targetY ?? 0.6
                )
                action = .playCard(card: card, position: target)
            } else {
                action = .none(reason: "カード '\(response.cardName ?? "不明")' が手札にありません")
            }

        case "wait":
            action = .wait(duration: 1.0)

        case "tap":
            let target = CGPoint(
                x: response.targetX ?? 0.5,
                y: response.targetY ?? 0.5
            )
            action = .tap(position: target)

        default:
            action = .none(reason: "不明なアクションタイプ: \(response.actionType)")
        }

        return AgentDecision(
            action: action,
            reasoning: response.reasoning ?? "理由なし",
            confidence: response.confidence ?? 0.5
        )
    }

    // MARK: - Private

    private static func parsePhase(_ phase: String) -> GameState.GamePhase {
        switch phase.lowercased() {
        case "battle": return .battle
        case "matchmaking": return .matchmaking
        case "overtime": return .overtime
        case "victory": return .victory
        case "defeat": return .defeat
        case "draw": return .draw
        default: return .unknown
        }
    }

    private static func convertTowerHP(_ towers: GameAnalysisResponse.TowerState, maxKing: Int, maxPrincess: Int) -> GameState.TowerHP {
        var hp = GameState.TowerHP()
        hp.king = (towers.kingHpPercent ?? 100) * maxKing / 100
        hp.leftPrincess = (towers.leftPrincessHpPercent ?? 100) * maxPrincess / 100
        hp.rightPrincess = (towers.rightPrincessHpPercent ?? 100) * maxPrincess / 100
        hp.leftPrincessDestroyed = towers.leftDestroyed ?? false
        hp.rightPrincessDestroyed = towers.rightDestroyed ?? false
        return hp
    }
}
