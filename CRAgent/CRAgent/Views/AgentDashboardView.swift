import SwiftUI

/// メインダッシュボード - エージェントの状態と制御
struct AgentDashboardView: View {
    @EnvironmentObject var coordinator: AgentCoordinator

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // ステータスカード
                statusCard

                // ゲーム状態
                gameStateCard

                // コントロールボタン
                controlButtons

                // 最新の判断
                if let decision = coordinator.lastDecision {
                    decisionCard(decision)
                }

                // 統計
                statsCard

                // ログ
                AgentLogView()
                    .frame(maxHeight: 300)
            }
            .padding()
        }
        .background(Color(.systemGroupedBackground))
    }

    // MARK: - ステータスカード

    private var statusCard: some View {
        HStack {
            Circle()
                .fill(coordinator.isRunning ? Color.green : Color.gray)
                .frame(width: 12, height: 12)
                .overlay {
                    if coordinator.isRunning {
                        Circle()
                            .fill(Color.green.opacity(0.3))
                            .frame(width: 20, height: 20)
                            .animation(.easeInOut(duration: 1).repeatForever(), value: coordinator.isRunning)
                    }
                }

            Text(coordinator.isRunning ? "稼働中" : "停止中")
                .font(.headline)

            Spacer()

            // モード選択
            Picker("モード", selection: $coordinator.mode) {
                ForEach(AgentCoordinator.AgentMode.allCases, id: \.self) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 220)
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5)
    }

    // MARK: - ゲーム状態カード

    private var gameStateCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "gamecontroller.fill")
                    .foregroundColor(.purple)
                Text("ゲーム状態")
                    .font(.headline)
                Spacer()
                Text(coordinator.currentGameState.phase.rawValue)
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(phaseColor.opacity(0.2))
                    .foregroundColor(phaseColor)
                    .cornerRadius(8)
            }

            // エリクサーバー
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("エリクサー")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Spacer()
                    Text("\(String(format: "%.1f", coordinator.currentGameState.elixir)) / 10")
                        .font(.caption.monospacedDigit())
                }

                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.purple.opacity(0.2))

                        RoundedRectangle(cornerRadius: 4)
                            .fill(
                                LinearGradient(
                                    colors: [.purple, .pink],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                            .frame(width: geo.size.width * CGFloat(coordinator.currentGameState.elixir / 10.0))
                    }
                }
                .frame(height: 8)
            }

            // 手札
            if !coordinator.currentGameState.handCards.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("手札")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    HStack(spacing: 8) {
                        ForEach(coordinator.currentGameState.handCards) { card in
                            VStack(spacing: 2) {
                                Text(card.name)
                                    .font(.caption2)
                                    .lineLimit(1)
                                Text("\(card.elixirCost)")
                                    .font(.caption2.bold())
                                    .foregroundColor(.purple)
                            }
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.purple.opacity(0.1))
                            .cornerRadius(6)
                        }
                    }
                }
            }

            // タワーHP
            HStack(spacing: 16) {
                towerHPView(
                    label: "自タワー",
                    tower: coordinator.currentGameState.myTowerHP,
                    color: .blue
                )
                towerHPView(
                    label: "敵タワー",
                    tower: coordinator.currentGameState.enemyTowerHP,
                    color: .red
                )
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5)
    }

    private func towerHPView(label: String, tower: GameState.TowerHP, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)

            HStack(spacing: 4) {
                towerIndicator("L", hp: tower.leftPrincess, max: 1400, destroyed: tower.leftPrincessDestroyed, color: color)
                towerIndicator("K", hp: tower.king, max: 2400, destroyed: false, color: color)
                towerIndicator("R", hp: tower.rightPrincess, max: 1400, destroyed: tower.rightPrincessDestroyed, color: color)
            }
        }
    }

    private func towerIndicator(_ label: String, hp: Int, max: Int, destroyed: Bool, color: Color) -> some View {
        VStack(spacing: 2) {
            Text(label)
                .font(.system(size: 9).bold())
            Text(destroyed ? "X" : "\(hp)")
                .font(.system(size: 8).monospacedDigit())
        }
        .frame(width: 36, height: 32)
        .background(destroyed ? Color.gray.opacity(0.3) : color.opacity(Double(hp) / Double(max) * 0.3 + 0.1))
        .cornerRadius(4)
    }

    private var phaseColor: Color {
        switch coordinator.currentGameState.phase {
        case .battle: return .green
        case .overtime, .tripleElixir: return .orange
        case .victory: return .blue
        case .defeat: return .red
        case .matchmaking: return .yellow
        default: return .gray
        }
    }

    // MARK: - コントロールボタン

    private var controlButtons: some View {
        HStack(spacing: 16) {
            Button {
                if coordinator.isRunning {
                    coordinator.stop()
                } else {
                    coordinator.start()
                }
            } label: {
                Label(
                    coordinator.isRunning ? "停止" : "開始",
                    systemImage: coordinator.isRunning ? "stop.fill" : "play.fill"
                )
                .font(.headline)
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(coordinator.isRunning ? Color.red : Color.green)
                .cornerRadius(12)
            }

            Button {
                coordinator.clearLogs()
            } label: {
                Label("ログ消去", systemImage: "trash")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .padding(.vertical, 14)
                    .padding(.horizontal, 16)
                    .background(Color(.systemGray6))
                    .cornerRadius(12)
            }
        }
    }

    // MARK: - 判断カード

    private func decisionCard(_ decision: AgentDecision) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "brain.head.profile")
                    .foregroundColor(.orange)
                Text("最新の判断")
                    .font(.headline)
                Spacer()
                Text("\(String(format: "%.0f%%", decision.confidence * 100))")
                    .font(.caption.bold())
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(confidenceColor(decision.confidence).opacity(0.2))
                    .foregroundColor(confidenceColor(decision.confidence))
                    .cornerRadius(8)
            }

            Text(decision.action.description)
                .font(.subheadline.bold())

            Text(decision.reasoning)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5)
    }

    private func confidenceColor(_ value: Double) -> Color {
        if value >= 0.7 { return .green }
        if value >= 0.4 { return .orange }
        return .red
    }

    // MARK: - 統計カード

    private var statsCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "chart.bar.fill")
                    .foregroundColor(.blue)
                Text("統計")
                    .font(.headline)
            }

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 12) {
                statItem("アクション", value: "\(coordinator.stats.totalActions)")
                statItem("カード配置", value: "\(coordinator.stats.cardsPlayed)")
                statItem("API呼出", value: "\(coordinator.stats.apiCalls)")
                statItem("成功率", value: coordinator.stats.totalActions > 0
                    ? "\(Int(Double(coordinator.stats.successfulActions) / Double(coordinator.stats.totalActions) * 100))%"
                    : "-")
                statItem("応答時間", value: coordinator.stats.averageResponseTime > 0
                    ? "\(String(format: "%.1f", coordinator.stats.averageResponseTime))s"
                    : "-")
                statItem("稼働時間", value: formatDuration(coordinator.stats.sessionDuration))
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5)
    }

    private func statItem(_ label: String, value: String) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title3.bold().monospacedDigit())
            Text(label)
                .font(.caption2)
                .foregroundColor(.secondary)
        }
    }

    private func formatDuration(_ seconds: TimeInterval) -> String {
        let mins = Int(seconds) / 60
        let secs = Int(seconds) % 60
        return "\(mins):\(String(format: "%02d", secs))"
    }
}
