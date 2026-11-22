// No UIKit: tests/launcher compiles this file on Linux.
import Foundation

/// What an edge swipe does (notes/nav-gestures.md).
enum NavAction: String {
    case back, home, appsList, none
}

/// The spec's settings model with its defaults; the UserDefaults store comes later.
struct NavigationSettings {
    var bindings: [String: NavAction] = [
        "left.inward": .appsList, "left.down": .home, "right.inward": .back, "right.down": .none,
    ]
    var stripWidth: (left: CGFloat, right: CGFloat) = (20, 20)
    var commitDistance: (inward: CGFloat, down: CGFloat) = (48, 96)

    static let current = NavigationSettings()
}

/// The spans of the side edges the app takes back (View.setSystemGestureExclusionRects), pt from the
/// top of the app's window.
struct EdgeExclusion: Equatable {
    var left: [ClosedRange<CGFloat>] = []
    var right: [ClosedRange<CGFloat>] = []
}

enum EdgeGesture {
    enum Edge: String { case left, right }
    enum Axis: String { case inward, down }

    static let commitVelocity: CGFloat = 600

    /// The edge whose strip `point` is in, between the safe area's top and bottom, unless the app
    /// excluded that part of it; the app's window starts `windowTop` down `bounds`.
    static func edge(at point: CGPoint, in bounds: CGRect, safeTop: CGFloat, safeBottom: CGFloat, windowTop: CGFloat,
                     settings: NavigationSettings, exclusion: EdgeExclusion = EdgeExclusion()) -> Edge? {
        guard point.y >= bounds.minY + safeTop, point.y <= bounds.maxY - safeBottom else { return nil }
        let edge: Edge
        if point.x <= bounds.minX + settings.stripWidth.left {
            edge = .left
        } else if point.x >= bounds.maxX - settings.stripWidth.right {
            edge = .right
        } else {
            return nil
        }
        let y = point.y - bounds.minY - windowTop
        return (edge == .left ? exclusion.left : exclusion.right).contains { $0.contains(y) } ? nil : edge
    }

    /// The dominant direction once the pan begins, if it is inward or down. The pan's own start
    /// threshold is the decision distance: a second one fails diagonal swipes.
    static func axis(edge: Edge, translation: CGPoint, velocity: CGPoint) -> Axis? {
        let move = translation == .zero ? velocity : translation
        if abs(move.x) >= abs(move.y) { return (edge == .left ? move.x : -move.x) > 0 ? .inward : nil }
        return move.y > 0 ? .down : nil
    }

    static func action(edge: Edge, axis: Axis, settings: NavigationSettings) -> NavAction {
        settings.bindings["\(edge.rawValue).\(axis.rawValue)"] ?? .none
    }

    /// Travel and speed along the axis, positive toward the commit.
    static func progress(edge: Edge, axis: Axis, translation: CGPoint, velocity: CGPoint) -> (CGFloat, CGFloat) {
        switch axis {
        case .inward: return edge == .left ? (translation.x, velocity.x) : (-translation.x, -velocity.x)
        case .down: return (translation.y, velocity.y)
        }
    }

    static func commits(axis: Axis, travel: CGFloat, speed: CGFloat, settings: NavigationSettings) -> Bool {
        let distance = axis == .inward ? settings.commitDistance.inward : settings.commitDistance.down
        return travel >= distance || speed >= commitVelocity
    }
}
