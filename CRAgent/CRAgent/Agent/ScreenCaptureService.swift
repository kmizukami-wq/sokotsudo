import Foundation
import UIKit
import ReplayKit

/// 画面キャプチャサービス - ReplayKitを使用してゲーム画面をキャプチャ
@MainActor
final class ScreenCaptureService: ObservableObject {

    @Published var isCapturing = false
    @Published var latestScreenshot: UIImage?
    @Published var error: String?

    private var captureTimer: Timer?
    private let captureInterval: TimeInterval

    init(captureInterval: TimeInterval = 1.0) {
        self.captureInterval = captureInterval
    }

    // MARK: - 画面キャプチャ開始/停止

    /// 定期的な画面キャプチャを開始
    func startCapturing() {
        guard !isCapturing else { return }

        isCapturing = true
        error = nil

        // ReplayKitでの録画開始
        let recorder = RPScreenRecorder.shared()

        guard recorder.isAvailable else {
            error = "画面録画が利用できません"
            isCapturing = false
            return
        }

        // 定期的にスクリーンショットを撮る
        captureTimer = Timer.scheduledTimer(withTimeInterval: captureInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.captureScreen()
            }
        }
    }

    /// キャプチャを停止
    func stopCapturing() {
        captureTimer?.invalidate()
        captureTimer = nil
        isCapturing = false
    }

    /// 単一フレームをキャプチャ
    func captureScreen() async {
        // iOS の画面キャプチャ方法:
        // 1. RPScreenRecorder の startCapture でサンプルバッファを取得
        // 2. UIScreen のスナップショット (非公開API)
        // 3. アプリ内のビューのみキャプチャ

        // ReplayKit の startCapture を使用
        await withCheckedContinuation { continuation in
            RPScreenRecorder.shared().startCapture { sampleBuffer, bufferType, error in
                guard bufferType == .video, error == nil else { return }

                if let image = self.imageFromSampleBuffer(sampleBuffer) {
                    Task { @MainActor in
                        self.latestScreenshot = image
                        // 1フレーム取得後に停止
                        RPScreenRecorder.shared().stopCapture { _ in }
                    }
                }
                continuation.resume()
            } completionHandler: { error in
                if error != nil {
                    // フォールバック: アプリ画面のスナップショット
                    Task { @MainActor in
                        self.latestScreenshot = self.captureAppScreen()
                        continuation.resume()
                    }
                }
            }
        }
    }

    // MARK: - スナップショット取得

    /// 現在のアプリ画面をキャプチャ（フォールバック）
    private func captureAppScreen() -> UIImage? {
        guard let window = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .first?.windows.first else { return nil }

        let renderer = UIGraphicsImageRenderer(bounds: window.bounds)
        return renderer.image { context in
            window.layer.render(in: context.cgContext)
        }
    }

    /// CMSampleBufferからUIImageに変換
    private func imageFromSampleBuffer(_ sampleBuffer: CMSampleBuffer) -> UIImage? {
        guard let imageBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return nil }

        let ciImage = CIImage(cvPixelBuffer: imageBuffer)
        let context = CIContext()

        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent) else { return nil }

        return UIImage(cgImage: cgImage)
    }

    // MARK: - 画像処理ユーティリティ

    /// スクリーンショットをリサイズ（API送信用に最適化）
    static func resizeForAPI(_ image: UIImage, maxDimension: CGFloat = 1024) -> UIImage {
        let size = image.size
        let ratio = min(maxDimension / size.width, maxDimension / size.height)

        if ratio >= 1.0 { return image }

        let newSize = CGSize(width: size.width * ratio, height: size.height * ratio)
        let renderer = UIGraphicsImageRenderer(size: newSize)
        return renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: newSize))
        }
    }

    /// 画面の特定領域を切り出し
    static func cropRegion(_ image: UIImage, rect: CGRect) -> UIImage? {
        let scale = image.scale
        let scaledRect = CGRect(
            x: rect.origin.x * image.size.width * scale,
            y: rect.origin.y * image.size.height * scale,
            width: rect.size.width * image.size.width * scale,
            height: rect.size.height * image.size.height * scale
        )

        guard let cgImage = image.cgImage?.cropping(to: scaledRect) else { return nil }
        return UIImage(cgImage: cgImage, scale: scale, orientation: image.imageOrientation)
    }

    /// 手札エリアのみを切り出し（画面下部）
    static func cropHandArea(_ image: UIImage) -> UIImage? {
        // クラロワの手札は画面最下部の約15%
        cropRegion(image, rect: CGRect(x: 0.1, y: 0.85, width: 0.8, height: 0.15))
    }

    /// エリクサーバーのみを切り出し
    static func cropElixirBar(_ image: UIImage) -> UIImage? {
        // エリクサーバーは手札の上
        cropRegion(image, rect: CGRect(x: 0.1, y: 0.82, width: 0.8, height: 0.04))
    }
}
