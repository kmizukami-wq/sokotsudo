import SwiftUI

/// 設定画面 - APIキーやエージェント設定
struct SettingsView: View {
    @EnvironmentObject var coordinator: AgentCoordinator
    @Environment(\.dismiss) private var dismiss

    @AppStorage("claude_api_key") private var apiKey = ""
    @AppStorage("claude_model") private var model = "claude-sonnet-4-6"
    @AppStorage("loop_interval") private var loopInterval: Double = 1.5
    @AppStorage("confidence_threshold") private var confidenceThreshold: Double = 0.3

    var body: some View {
        NavigationStack {
            Form {
                // API設定
                Section("Claude API設定") {
                    SecureField("APIキー", text: $apiKey)
                        .textContentType(.password)
                        .autocorrectionDisabled()

                    Picker("モデル", selection: $model) {
                        Text("Claude Sonnet 4.6 (推奨)").tag("claude-sonnet-4-6")
                        Text("Claude Haiku 4.5 (高速)").tag("claude-haiku-4-5-20251001")
                        Text("Claude Opus 4.6 (高精度)").tag("claude-opus-4-6")
                    }

                    Button("APIキーを適用") {
                        guard !apiKey.isEmpty else { return }
                        coordinator.configureAPI(apiKey: apiKey, model: model)
                    }
                    .disabled(apiKey.isEmpty)
                }

                // エージェント設定
                Section("エージェント設定") {
                    VStack(alignment: .leading) {
                        Text("ループ間隔: \(String(format: "%.1f", loopInterval))秒")
                        Slider(value: $loopInterval, in: 0.5...5.0, step: 0.5)
                    }
                    .onChange(of: loopInterval) { _, newValue in
                        coordinator.setLoopInterval(newValue)
                    }

                    VStack(alignment: .leading) {
                        Text("確信度しきい値: \(String(format: "%.0f%%", confidenceThreshold * 100))")
                        Slider(value: $confidenceThreshold, in: 0.0...1.0, step: 0.1)
                    }
                    .onChange(of: confidenceThreshold) { _, newValue in
                        coordinator.setConfidenceThreshold(newValue)
                    }
                }

                // 操作説明
                Section("使い方") {
                    VStack(alignment: .leading, spacing: 8) {
                        instructionRow("1", "Claude APIキーを入力して「適用」")
                        instructionRow("2", "クラッシュロワイヤルを起動")
                        instructionRow("3", "このアプリに戻り「開始」をタップ")
                        instructionRow("4", "クラッシュロワイヤルに切り替え")
                        instructionRow("5", "AIがゲーム画面を分析して自動操作")
                    }
                }

                // モード説明
                Section("モード説明") {
                    modeDescription("AI支援", "Claude APIで画面を分析し、AIが最適な操作を判断・実行します")
                    modeDescription("ローカル", "API不要。内蔵ロジックで基本的な戦略判断を行います")
                    modeDescription("観察のみ", "画面分析のみ行い、操作は実行しません。テスト用")
                }

                // 注意事項
                Section("注意事項") {
                    Text("このアプリは研究・教育目的で開発されています。ゲームの利用規約を確認の上、自己責任でご使用ください。")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .navigationTitle("設定")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("完了") { dismiss() }
                }
            }
        }
    }

    private func instructionRow(_ number: String, _ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Text(number)
                .font(.caption.bold())
                .frame(width: 20, height: 20)
                .background(Color.blue.opacity(0.2))
                .cornerRadius(10)
            Text(text)
                .font(.caption)
        }
    }

    private func modeDescription(_ title: String, _ description: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.subheadline.bold())
            Text(description)
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}
