import UIKit

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

enum EdgeGesture {
    enum Edge: String { case left, right }
    enum Axis: String { case inward, down }

    static let decideDistance: CGFloat = 10
    static let commitVelocity: CGFloat = 600

    /// The edge whose strip `point` is in, between the safe area's top and bottom.
    static func edge(at point: CGPoint, in bounds: CGRect, safeArea: UIEdgeInsets, settings: NavigationSettings) -> Edge? {
        guard point.y >= bounds.minY + safeArea.top, point.y <= bounds.maxY - safeArea.bottom else { return nil }
        if point.x <= bounds.minX + settings.stripWidth.left { return .left }
        if point.x >= bounds.maxX - settings.stripWidth.right { return .right }
        return nil
    }

    /// The axis once the touch moved far enough: the dominant one, if it is inward or down.
    static func axis(edge: Edge, translation: CGPoint) -> Axis? {
        let inward = edge == .left ? translation.x : -translation.x
        guard max(abs(translation.x), abs(translation.y)) >= decideDistance else { return nil }
        if abs(translation.x) >= abs(translation.y) { return inward > 0 ? .inward : nil }
        return translation.y > 0 ? .down : nil
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

/// Edge swipes on one view: a pan that only takes touches starting in an edge strip, then picks its
/// binding by the dominant axis and commits on release. `allows` filters the actions this view takes.
@MainActor
final class EdgeGestureRecognizer: NSObject, UIGestureRecognizerDelegate {
    private let allows: (NavAction) -> Bool
    private let perform: (NavAction) -> Void
    private let pan = UIPanGestureRecognizer()
    private let indicator = UIImageView()
    private var edge: EdgeGesture.Edge?
    private var axis: EdgeGesture.Axis?

    init(on view: UIView, allows: @escaping (NavAction) -> Bool, perform: @escaping (NavAction) -> Void) {
        self.allows = allows
        self.perform = perform
        super.init()
        pan.delegate = self
        pan.cancelsTouchesInView = true
        pan.maximumNumberOfTouches = 1
        pan.addTarget(self, action: #selector(panned))
        view.addGestureRecognizer(pan)
        indicator.tintColor = .label
        indicator.backgroundColor = .secondarySystemBackground
        indicator.contentMode = .center
        indicator.layer.cornerRadius = 22
        indicator.frame.size = CGSize(width: 44, height: 44)
        indicator.isHidden = true
    }

    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldReceive touch: UITouch) -> Bool {
        // a second finger mid-swipe must not reset it
        guard pan.state == .possible, let view = pan.view else { return false }
        edge = EdgeGesture.edge(at: touch.location(in: view), in: view.bounds, safeArea: view.safeAreaInsets,
                                settings: .current)
        axis = nil
        guard let edge else { return false }
        return [EdgeGesture.Axis.inward, .down].contains { axis in
            let action = EdgeGesture.action(edge: edge, axis: axis, settings: .current)
            return action != .none && allows(action)
        }
    }

    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        guard let edge, let view = pan.view,
              let axis = EdgeGesture.axis(edge: edge, translation: pan.translation(in: view)) else { return false }
        let action = EdgeGesture.action(edge: edge, axis: axis, settings: .current)
        guard action != .none, allows(action) else { return false }
        self.axis = axis
        return true
    }

    @objc private func panned() {
        guard let edge, let axis, let view = pan.view else { return }
        let action = EdgeGesture.action(edge: edge, axis: axis, settings: .current)
        let (travel, speed) = EdgeGesture.progress(edge: edge, axis: axis, translation: pan.translation(in: view),
                                                   velocity: pan.velocity(in: view))
        switch pan.state {
        case .began, .changed:
            if indicator.superview !== view {
                view.addSubview(indicator)
            }
            indicator.image = UIImage(systemName: Self.symbol(action))
            indicator.isHidden = false
            indicator.center = pan.location(in: view)
            let commits = EdgeGesture.commits(axis: axis, travel: travel, speed: 0, settings: .current)
            indicator.alpha = commits ? 1 : 0.4
        case .ended:
            indicator.isHidden = true
            if EdgeGesture.commits(axis: axis, travel: travel, speed: speed, settings: .current) {
                perform(action)
            }
        default:
            indicator.isHidden = true
        }
    }

    private static func symbol(_ action: NavAction) -> String {
        switch action {
        case .back: "chevron.backward"
        case .home: "house"
        case .appsList: "square.stack"
        case .none: "xmark"
        }
    }
}
