import Foundation

/// クラッシュロワイヤルのカード情報
struct Card: Identifiable, Codable, Equatable {
    let id: String
    let name: String
    let elixirCost: Int
    let cardType: CardType

    enum CardType: String, Codable {
        case troop      // ユニット
        case spell      // 呪文
        case building   // 建物
    }
}

// MARK: - クラロワ主要カード定義
extension Card {
    static let knownCards: [Card] = [
        // ユニット系
        Card(id: "knight", name: "ナイト", elixirCost: 3, cardType: .troop),
        Card(id: "archers", name: "アーチャー", elixirCost: 3, cardType: .troop),
        Card(id: "giant", name: "ジャイアント", elixirCost: 5, cardType: .troop),
        Card(id: "minipekka", name: "ミニP.E.K.K.A", elixirCost: 4, cardType: .troop),
        Card(id: "musketeer", name: "マスケット銃士", elixirCost: 4, cardType: .troop),
        Card(id: "hog_rider", name: "ホグライダー", elixirCost: 4, cardType: .troop),
        Card(id: "valkyrie", name: "バルキリー", elixirCost: 4, cardType: .troop),
        Card(id: "wizard", name: "ウィザード", elixirCost: 5, cardType: .troop),
        Card(id: "witch", name: "ウィッチ", elixirCost: 5, cardType: .troop),
        Card(id: "skeleton_army", name: "スケルトン部隊", elixirCost: 3, cardType: .troop),
        Card(id: "minions", name: "ガーゴイル", elixirCost: 3, cardType: .troop),
        Card(id: "goblin_barrel", name: "ゴブリンバレル", elixirCost: 3, cardType: .spell),
        Card(id: "balloon", name: "エアバルーン", elixirCost: 5, cardType: .troop),
        Card(id: "pekka", name: "P.E.K.K.A", elixirCost: 7, cardType: .troop),
        Card(id: "golem", name: "ゴーレム", elixirCost: 8, cardType: .troop),
        Card(id: "lava_hound", name: "ラヴァハウンド", elixirCost: 7, cardType: .troop),
        Card(id: "electro_wizard", name: "エレクトロウィザード", elixirCost: 4, cardType: .troop),
        Card(id: "mega_knight", name: "メガナイト", elixirCost: 7, cardType: .troop),
        Card(id: "royal_giant", name: "ロイヤルジャイアント", elixirCost: 6, cardType: .troop),
        Card(id: "sparky", name: "スパーキー", elixirCost: 6, cardType: .troop),

        // 呪文系
        Card(id: "fireball", name: "ファイアボール", elixirCost: 4, cardType: .spell),
        Card(id: "arrows", name: "矢の雨", elixirCost: 3, cardType: .spell),
        Card(id: "zap", name: "ザップ", elixirCost: 2, cardType: .spell),
        Card(id: "log", name: "ローリングウッド", elixirCost: 2, cardType: .spell),
        Card(id: "lightning", name: "ライトニング", elixirCost: 6, cardType: .spell),
        Card(id: "rocket", name: "ロケット", elixirCost: 6, cardType: .spell),
        Card(id: "poison", name: "ポイズン", elixirCost: 4, cardType: .spell),
        Card(id: "freeze", name: "フリーズ", elixirCost: 4, cardType: .spell),
        Card(id: "tornado", name: "トルネード", elixirCost: 3, cardType: .spell),

        // 建物系
        Card(id: "cannon", name: "大砲", elixirCost: 3, cardType: .building),
        Card(id: "tesla", name: "テスラ", elixirCost: 4, cardType: .building),
        Card(id: "inferno_tower", name: "インフェルノタワー", elixirCost: 5, cardType: .building),
        Card(id: "bomb_tower", name: "ボムタワー", elixirCost: 4, cardType: .building),
        Card(id: "xbow", name: "クロスボウ", elixirCost: 6, cardType: .building),
        Card(id: "mortar", name: "迫撃砲", elixirCost: 4, cardType: .building),
    ]

    static func find(byName name: String) -> Card? {
        knownCards.first { $0.name == name || $0.id == name }
    }
}
