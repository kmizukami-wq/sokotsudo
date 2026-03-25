import SwiftUI

/// エージェントのログ表示ビュー
struct AgentLogView: View {
    @EnvironmentObject var coordinator: AgentCoordinator

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "list.bullet.rectangle")
                    .foregroundColor(.green)
                Text("ログ")
                    .font(.headline)
                Spacer()
                Text("\(coordinator.logs.count)件")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            if coordinator.logs.isEmpty {
                Text("ログはまだありません")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding()
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 6) {
                        ForEach(coordinator.logs) { entry in
                            logEntryView(entry)
                        }
                    }
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 5)
    }

    private func logEntryView(_ entry: AgentLogEntry) -> some View {
        HStack(alignment: .top, spacing: 8) {
            // レベルインジケーター
            Text(levelIcon(entry.level))
                .font(.caption2)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 2) {
                Text(entry.message)
                    .font(.caption)
                    .foregroundColor(levelColor(entry.level))
                    .lineLimit(3)

                Text(formatTime(entry.timestamp))
                    .font(.system(size: 9).monospacedDigit())
                    .foregroundColor(.secondary)
            }
        }
        .padding(.vertical, 2)
    }

    private func levelIcon(_ level: AgentLogEntry.LogLevel) -> String {
        switch level {
        case .info: return "ℹ️"
        case .action: return "⚡"
        case .warning: return "⚠️"
        case .error: return "❌"
        case .thinking: return "🧠"
        }
    }

    private func levelColor(_ level: AgentLogEntry.LogLevel) -> Color {
        switch level {
        case .info: return .primary
        case .action: return .blue
        case .warning: return .orange
        case .error: return .red
        case .thinking: return .purple
        }
    }

    private func formatTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return formatter.string(from: date)
    }
}
