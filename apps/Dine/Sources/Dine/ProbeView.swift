import OSLog
import SwiftUI
import UIKit

private let log = Logger(subsystem: "dev.dine.Dine", category: "probe")

/// Loads every asset kind accord compiled into Assets.car and logs `probe <kind> <name> ok|FAIL …`,
/// then `probe done`.
struct ProbeView: View {
    @State private var lines: [String] = []

    var body: some View {
        List {
            Section {
                HStack(spacing: 16) {
                    Image("ProbeGlyph")
                    Image("ProbeVector")
                    Image("ProbeBadge")
                    Color("ProbeColor").frame(width: 32, height: 32)
                }
            }
            Section("Alternate icon") {
                Button("Use classic icon") { setIcon("AppIconClassic") }
                Button("Use default icon") { setIcon(nil) }
            }
            Section("Checks") {
                ForEach(lines, id: \.self) { Text($0).font(.caption.monospaced()) }
            }
        }
        .navigationTitle("probe")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear(perform: run)
    }

    private func run() {
        guard lines.isEmpty else { return }
        image("ProbeGlyph", size: CGSize(width: 32, height: 32), at: CGPoint(x: 16, y: 16), rgb: [61, 220, 132])
        image("ProbeVector", size: CGSize(width: 24, height: 24), at: CGPoint(x: 12, y: 16), rgb: [140, 26, 64])
        image("ProbeBadge", size: CGSize(width: 30, height: 30), at: CGPoint(x: 15, y: 15), rgb: [61, 219, 133])
        // An AppIcon.icon layer (gray + alpha): the star's centre, right arm and lower arm.
        for (i, at) in [CGPoint(x: 770, y: 230), CGPoint(x: 810, y: 230), CGPoint(x: 770, y: 270)].enumerated() {
            image("AppIcon_Assets/sparkles", size: CGSize(width: 1024, height: 1024), at: at, rgb: [255, 255, 255], tag: "\(i)")
        }
        color("ProbeColor", light: [0, 0, 255], dark: [255, 128, 0])
        color("AccentColor", light: nil, dark: nil)
        let data = NSDataAsset(name: "ProbeData")
        let text = data.map { String(decoding: $0.data, as: UTF8.self) } ?? "nil"
        report(text.contains("\"accord\"") && data?.typeIdentifier == "public.json", "data ProbeData", "\(text.trimmingCharacters(in: .whitespacesAndNewlines)) type=\(data?.typeIdentifier ?? "nil")")
        let icons = Bundle.main.object(forInfoDictionaryKey: "CFBundleIcons") as? [String: Any]
        let primary = icons?["CFBundlePrimaryIcon"] as? [String: Any]
        report(primary?["CFBundleIconName"] as? String == "AppIcon", "plist CFBundleIcons",
               "primary=\(primary?["CFBundleIconName"] ?? "nil") alternates=\((icons?["CFBundleAlternateIcons"] as? [String: Any])?.keys.sorted() ?? [])")
        report(UIApplication.shared.supportsAlternateIcons, "app alternate-icons",
               "current=\(UIApplication.shared.alternateIconName ?? "default")")
        let fails = lines.filter { $0.contains(" FAIL") }.count
        log.notice("probe done \(lines.count - fails, privacy: .public) ok \(fails, privacy: .public) fail")
    }

    private func image(_ name: String, size: CGSize, at point: CGPoint, rgb: [Int], tag: String = "") {
        let what = "image \(name)\(tag.isEmpty ? "" : "#\(tag)")"
        guard let img = UIImage(named: name) else { return report(false, what, "nil") }
        let px = pixel(img, at: point)
        let ok = img.size == size && zip(px, rgb).allSatisfy { abs($0 - $1) <= 8 } && px[3] == 255
        report(ok, what, "\(Int(img.size.width))x\(Int(img.size.height))@\(Int(img.scale)) px=\(px)")
    }

    /// nil expectations: only check that light and dark resolve to different colours.
    private func color(_ name: String, light: [Int]?, dark: [Int]?) {
        guard let c = UIColor(named: name) else { return report(false, "color \(name)", "nil") }
        let l = components(c.resolvedColor(with: UITraitCollection(userInterfaceStyle: .light)))
        let d = components(c.resolvedColor(with: UITraitCollection(userInterfaceStyle: .dark)))
        let near = { (a: [Int], b: [Int]) in zip(a, b).allSatisfy { abs($0 - $1) <= 2 } }
        let ok = light.map { near(l, $0) && near(d, dark!) } ?? (l != d)
        report(ok, "color \(name)", "light=\(l) dark=\(d)")
    }

    private func setIcon(_ name: String?) {
        Task {
            do {
                try await UIApplication.shared.setAlternateIconName(name)
                report(true, "alt-icon \(name ?? "default")", "set")
            } catch {
                report(false, "alt-icon \(name ?? "default")", "\(error)")
            }
        }
    }

    private func report(_ ok: Bool, _ what: String, _ detail: String) {
        let line = "probe \(what) \(ok ? "ok" : "FAIL") \(detail)"
        log.notice("\(line, privacy: .public)")
        lines.append(line)
    }
}

/// sRGB 0-255 of one point of `image`, drawn at 1 pixel per point.
private func pixel(_ image: UIImage, at p: CGPoint) -> [Int] {
    var px = [UInt8](repeating: 0, count: 4)
    px.withUnsafeMutableBytes { buf in
        let ctx = CGContext(
            data: buf.baseAddress, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
            space: CGColorSpace(name: CGColorSpace.sRGB)!,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        // UIKit draws top-down; a bare CGContext is bottom-up.
        ctx.translateBy(x: 0, y: 1)
        ctx.scaleBy(x: 1, y: -1)
        UIGraphicsPushContext(ctx)
        image.draw(at: CGPoint(x: -p.x, y: -p.y))
        UIGraphicsPopContext()
    }
    return px.map(Int.init)
}

private func components(_ c: UIColor) -> [Int] {
    var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
    c.getRed(&r, green: &g, blue: &b, alpha: &a)
    return [r, g, b, a].map { Int(($0 * 255).rounded()) }
}
