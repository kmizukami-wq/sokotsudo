import Foundation

/// クラッシュロワイヤルのゲーム状態
struct GameState {
    var phase: GamePhase = .unknown
    var elixir: Double = 0
    var handCards: [Card] = []
    var nextCard: Card? = nil
    var myTowerHP: TowerHP = TowerHP()
    var enemyTowerHP: TowerHP = TowerHP()
    var activeUnits: [DetectedUnit] = []
    var timeRemaining: TimeInterval = 180
    var isDoubleElixir: Bool = false
    var isTripleElixir: Bool = false

    enum GamePhase: String {
        case unknown        // 不明
        case matchmaking    // マッチメイキング中
        case battle         // バトル中
        case overtime       // 延長戦
        case tripleElixir   // 3倍エリクサー
        case victory        // 勝利
        case defeat         // 敗北
        case draw           // 引き分け
    }

    struct TowerHP {
        var king: Int = 2400
        var leftPrincess: Int = 1400
        var rightPrincess: Int = 1400
        var leftPrincessDestroyed: Bool = false
        var rightPrincessDestroyed: Bool = false
        var kingActivated: Bool = false
    }

    struct DetectedUnit {
        let name: String
        let position: CGPoint       // 画面上の正規化座標 (0-1)
        let isEnemy: Bool
        let estimatedHP: Double?    // 0.0 - 1.0 (HP残り割合)
    }
}

// MARK: - ゲーム状態分析ヘルパー
extension GameState {

    /// エリクサーが足りるカードを取得
    var playableCards: [Card] {
        handCards.filter { Double($0.elixirCost) <= elixir }
    }

    /// 緊急防衛が必要かどうか
    var needsDefense: Bool {
        let enemyUnitsNearTower = activeUnits.filter { $0.isEnemy && $0.position.y > 0.6 }
        return !enemyUnitsNearTower.isEmpty
    }

    /// 攻撃チャンスかどうか
    var canCounterAttack: Bool {
        let myUnitsOnEnemySide = activeUnits.filter { !$0.isEnemy && $0.position.y < 0.4 }
        return myUnitsOnEnemySide.count >= 2 && elixir >= 4
    }

    /// より弱い敵タワーの方向
    var weakerEnemyTowerSide: FieldSide {
        if enemyTowerHP.leftPrincessDestroyed { return .right }
        if enemyTowerHP.rightPrincessDestroyed { return .left }
        return enemyTowerHP.leftPrincess <= enemyTowerHP.rightPrincess ? .left : .right
    }

    enum FieldSide {
        case left, right, center
    }
}
