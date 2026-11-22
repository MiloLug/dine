import OSLog
import UIKit

private let log = Logger(subsystem: "dev.dine.Dine", category: "art")

/// Edge swipes on one view: a pan that only takes touches starting in an edge strip, then picks its
/// binding by the dominant axis and commits on release. `allows` filters the actions this view takes.
@MainActor
final class EdgeGestureRecognizer: NSObject, UIGestureRecognizerDelegate {
    private let allows: (NavAction) -> Bool
    private let perform: (NavAction) -> Void
    private let exclusion: () -> EdgeExclusion
    private let windowTop: () -> CGFloat
    private let pan = UIPanGestureRecognizer()
    private let indicator = UIImageView()
    private var edge: EdgeGesture.Edge?
    private var axis: EdgeGesture.Axis?

    /// `windowTop`: where the app's window starts in the view, which its exclusion spans count from
    init(on view: UIView, allows: @escaping (NavAction) -> Bool, perform: @escaping (NavAction) -> Void,
         exclusion: @escaping () -> EdgeExclusion = { EdgeExclusion() }, windowTop: @escaping () -> CGFloat = { 0 }) {
        self.allows = allows
        self.perform = perform
        self.exclusion = exclusion
        self.windowTop = windowTop
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
        edge = EdgeGesture.edge(at: touch.location(in: view), in: view.bounds, safeTop: view.safeAreaInsets.top,
                                safeBottom: view.safeAreaInsets.bottom, windowTop: windowTop(), settings: .current,
                                exclusion: exclusion())
        axis = nil
        guard let edge else { return false }
        return [EdgeGesture.Axis.inward, .down].contains { axis in
            let action = EdgeGesture.action(edge: edge, axis: axis, settings: .current)
            return action != .none && allows(action)
        }
    }

    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        guard let edge, let view = pan.view else { return false }
        guard let axis = EdgeGesture.axis(edge: edge, translation: pan.translation(in: view), velocity: pan.velocity(in: view)) else {
            log.notice("nav: swipe \(edge.rawValue, privacy: .public) neither inward nor down")
            return false
        }
        let action = EdgeGesture.action(edge: edge, axis: axis, settings: .current)
        guard action != .none, allows(action) else {
            log.notice("nav: swipe \(edge.rawValue, privacy: .public) \(axis.rawValue, privacy: .public) has no action here")
            return false
        }
        self.axis = axis
        return true
    }

    // other recognizers (a scroll view's pan) wait while a touch from a strip may still be a swipe
    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer,
                           shouldBeRequiredToFailBy otherGestureRecognizer: UIGestureRecognizer) -> Bool {
        edge != nil
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
            let commits = EdgeGesture.commits(axis: axis, travel: travel, speed: speed, settings: .current)
            log.notice("nav: swipe \(edge.rawValue, privacy: .public) \(axis.rawValue, privacy: .public) \(commits ? "commits" : "cancels", privacy: .public): \(Int(travel)) pt, \(Int(speed)) pt/s")
            if commits {
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
