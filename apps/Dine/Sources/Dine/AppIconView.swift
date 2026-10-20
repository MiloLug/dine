import SwiftUI

/// Apps have no icon of their own until APK import: the default glyph on a colour from the name.
struct AppIconView: View {
    let name: String

    private static let size: CGFloat = 60

    var body: some View {
        VStack(spacing: 6) {
            RoundedRectangle(cornerRadius: Self.size * 0.225, style: .continuous)
                .fill(LinearGradient(
                    colors: [color(brightness: 0.95), color(brightness: 0.7)],
                    startPoint: .top, endPoint: .bottom))
                .frame(width: Self.size, height: Self.size)
                .overlay {
                    Image(decorative: "DefaultApp")
                        .renderingMode(.template)
                        .resizable()
                        .scaledToFit()
                        .frame(width: Self.size * 0.55)
                        .foregroundStyle(.white)
                }
                .shadow(color: .black.opacity(0.15), radius: 3, y: 1)
            Text(name)
                .font(.system(size: 12))
                .lineLimit(1)
                .truncationMode(.tail)
                .frame(maxWidth: Self.size + 16)
        }
    }

    private func color(brightness: Double) -> Color {
        Color(hue: hue, saturation: 0.65, brightness: brightness)
    }

    /// Stable per name (FNV-1a); `hashValue` is reseeded every launch.
    private var hue: Double {
        var hash: UInt32 = 2_166_136_261
        for byte in name.utf8 {
            hash = (hash ^ UInt32(byte)) &* 16_777_619
        }
        return Double(hash % 360) / 360
    }
}
