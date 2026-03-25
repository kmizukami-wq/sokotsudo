import SwiftUI
import UIKit

/// ゲーム画面上に表示するオーバーレイ
/// ピクチャインピクチャ的にエージェント状態を表示
struct OverlayIndicator: View {
    @EnvironmentObject var coordinator: AgentCoordinator
    @State private var isExpanded = false

    var body: some View {
        VStack(spacing: 0) {
            // ミニ表示
            HStack(spacing: 8) {
                Circle()
                    .fill(coordinator.isRunning ? Color.green : Color.gray)
                    .frame(width: 8, height: 8)

                if isExpanded {
                    Text(coordinator.isRunning ? "AI稼働中" : "AI停止")
                        .font(.caption2)
                        .foregroundColor(.white)
                }

                if isExpanded, let decision = coordinator.lastDecision {
                    Text("(\(String(format: "%.0f%%", decision.confidence * 100)))")
                        .font(.system(size: 9).monospacedDigit())
                        .foregroundColor(.white.opacity(0.7))
                }
            }
            .padding(.horizontal, isExpanded ? 12 : 8)
            .padding(.vertical, 6)
            .background(Color.black.opacity(0.7))
            .cornerRadius(16)
            .onTapGesture {
                withAnimation(.spring(response: 0.3)) {
                    isExpanded.toggle()
                }
            }

            // 展開時の詳細
            if isExpanded {
                VStack(alignment: .leading, spacing: 4) {
                    if let decision = coordinator.lastDecision {
                        Text(decision.action.description)
                            .font(.system(size: 10))
                            .foregroundColor(.white)
                            .lineLimit(2)
                    }

                    HStack(spacing: 8) {
                        miniStat("E", "\(String(format: "%.0f", coordinator.currentGameState.elixir))")
                        miniStat("A", "\(coordinator.stats.totalActions)")
                        miniStat("C", "\(coordinator.stats.cardsPlayed)")
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color.black.opacity(0.6))
                .cornerRadius(8)
                .transition(.opacity.combined(with: .scale))
            }
        }
    }

    private func miniStat(_ label: String, _ value: String) -> some View {
        HStack(spacing: 2) {
            Text(label)
                .font(.system(size: 8).bold())
                .foregroundColor(.white.opacity(0.5))
            Text(value)
                .font(.system(size: 10).monospacedDigit())
                .foregroundColor(.white)
        }
    }
}

// MARK: - フローティングオーバーレイウィンドウマネージャー

@MainActor
final class OverlayWindowManager {
    static let shared = OverlayWindowManager()

    private var overlayWindow: UIWindow?

    /// オーバーレイウィンドウを表示
    func show(coordinator: AgentCoordinator) {
        guard overlayWindow == nil else { return }

        guard let scene = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .first else { return }

        let window = PassthroughWindow(windowScene: scene)
        window.windowLevel = .alert + 1
        window.backgroundColor = .clear
        window.isHidden = false

        let hostingController = UIHostingController(
            rootView: OverlayIndicator()
                .environmentObject(coordinator)
        )
        hostingController.view.backgroundColor = .clear

        window.rootViewController = hostingController

        // 画面右上に配置
        let width: CGFloat = 160
        let height: CGFloat = 80
        window.frame = CGRect(
            x: UIScreen.main.bounds.width - width - 16,
            y: 60,
            width: width,
            height: height
        )

        self.overlayWindow = window
    }

    /// オーバーレイウィンドウを非表示
    func hide() {
        overlayWindow?.isHidden = true
        overlayWindow = nil
    }
}

/// タッチを透過するウィンドウ
final class PassthroughWindow: UIWindow {
    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
        let view = super.hitTest(point, with: event)
        // ルートビュー自体へのタッチは透過する
        return view == rootViewController?.view ? nil : view
    }
}
