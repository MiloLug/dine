import CArtBridge
import OSLog
import SwiftUI
import UIKit

private let log = Logger(subsystem: "dev.dine.Dine", category: "art")

/// Back, Home, the app's container and the running apps list (notes/nav-gestures.md), for the one
/// app ATL runs per process. Dine's UI changes first, then ATL hears: Home never waits for Java.
@MainActor
final class Navigator: ObservableObject {
    @Published var path = NavigationPath()

    private var app: String?  // while ATL runs it
    private var surface: (view: AppSurfaceView, size: CGSize)?  // ATL's window, while ATL runs
    private var container: AppContainerController?
    private var appsList: AppsListController?
    private var listReturnsToApp = false
    private var keepScreenOn = false  // the app asks; it applies while its container shows
    private(set) var exclusion = EdgeExclusion()  // the shown activity's
    private var insetsSent: [Float] = []
    private var listener = atl_embedded_listener()
    private var launcherEdges: EdgeGestureRecognizer?

    init() {
        // the navigator lives as long as the app (DineMain's state object)
        listener.context = Unmanaged.passUnretained(self).toOpaque()
        listener.task_moved = { context, front, byHost in
            let navigator = Unmanaged<Navigator>.fromOpaque(context!).takeUnretainedValue()
            DispatchQueue.main.async { MainActor.assumeIsolated { navigator.taskMoved(front: front, byHost: byHost) } }
        }
        listener.exited = { context, _ in
            let navigator = Unmanaged<Navigator>.fromOpaque(context!).takeUnretainedValue()
            DispatchQueue.main.async { MainActor.assumeIsolated { navigator.exited() } }
        }
        listener.exclusion_changed = { context, exclusion in
            let navigator = Unmanaged<Navigator>.fromOpaque(context!).takeUnretainedValue()
            let spans = EdgeExclusion(exclusion!.pointee)
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    navigator.exclusion = spans
                    log.notice("nav: exclusion left \(spans.left.count) right \(spans.right.count)")
                }
            }
        }
        listener.keep_screen_on = { context, on in
            let navigator = Unmanaged<Navigator>.fromOpaque(context!).takeUnretainedValue()
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    navigator.keepScreenOn = on
                    navigator.updateIdleTimer()
                }
            }
        }
    }

    /// `start` runs ATL with the app's window and the listener; on success the app's container
    /// comes up.
    func run(_ app: String, start: (UnsafePointer<dine_atl_window>, UnsafePointer<atl_embedded_listener>) -> Int32) {
        guard let keyWindow = rootController?.view.window else {
            return log.error("atl: no key window to size the app's window from")
        }
        // below the status bar to the screen's bottom: the app gets the home indicator as insets
        let safeArea = keyWindow.safeAreaLayoutGuide.layoutFrame
        let size = CGSize(width: safeArea.width, height: keyWindow.bounds.maxY - safeArea.minY)
        let traits = keyWindow.traitCollection
        let scale = traits.displayScale
        let view = AppSurfaceView()
        let night: Int32 = switch traits.userInterfaceStyle {
        case .dark: 0x20  // Configuration.UI_MODE_NIGHT_YES
        case .light: 0x10
        default: 0
        }
        sendInsets(safeArea: keyWindow.safeAreaInsets)
        let window = dine_atl_window(view: Unmanaged.passUnretained(view).toOpaque(),
                                     width: Int32((size.width * scale).rounded(.down)),
                                     height: Int32((size.height * scale).rounded(.down)),
                                     density_dpi: Int32((160 * scale).rounded()), night: night)
        let started = withUnsafePointer(to: window) { window in
            withUnsafePointer(to: listener) { start(window, $0) }
        }
        guard started == 0 else { return }
        self.app = app
        surface = (view, CGSize(width: CGFloat(window.width) / scale, height: CGFloat(window.height) / scale))
        showContainer()
    }

    func back() {
        _ = atl_nav_back()
    }

    func home() {
        guard container != nil else { return }
        dismissContainer("home")
        popToRoot()
        _ = atl_nav_home()
    }

    /// From the app it moves the app to the back; dismissing the list brings it back.
    func openAppsList() {
        guard appsList == nil else { return }
        listReturnsToApp = container != nil
        if listReturnsToApp {
            _ = atl_nav_home()
        }
        let list = AppsListController(navigator: self, appRuns: app != nil)
        appsList = list
        dismissContainer("list") { [self] in
            afterTransitions { [self] in
                guard appsList === list else { return }
                rootController?.present(list, animated: true)
                log.notice("nav: apps list shown")
            }
        }
    }

    func perform(_ action: NavAction) {
        switch action {
        case .back: back()
        case .home: home()
        case .appsList: openAppsList()
        case .none: break
        }
    }

    /// The running apps list from the launcher's hosting view, by edge swipe or "Recent apps", only
    /// while nothing is pushed or presented: pushed screens keep iOS's own left-edge pop.
    func attachLauncher() {
        let navigator = self
        guard launcherEdges == nil, let view = rootController?.view else { return }
        launcherEdges = EdgeGestureRecognizer(on: view, allows: { action in
            action == .appsList && navigator.path.isEmpty && navigator.container == nil && navigator.appsList == nil
        }, perform: { navigator.perform($0) })
        view.accessibilityCustomActions = [
            UIAccessibilityCustomAction(name: "Recent apps") { _ in
                MainActor.assumeIsolated {
                    guard navigator.path.isEmpty, navigator.container == nil, navigator.appsList == nil else { return false }
                    navigator.openAppsList()
                    return true
                }
            },
        ]
    }

    func backToApp() {
        guard let list = appsList else { return }
        appsList = nil
        list.dismiss(animated: true) { [self] in front() }
    }

    func appsListSwipedAway() {
        appsList = nil
        if listReturnsToApp {
            front()
        }
    }

    private var rootController: UIViewController? {
        UIApplication.shared.connectedScenes.compactMap { ($0 as? UIWindowScene)?.keyWindow }.first?.rootViewController
    }

    private func front() {
        guard app != nil else { return }
        _ = atl_nav_front()
        showContainer()
    }

    /// UIKit drops a present or dismiss asked for while another one animates.
    private func afterTransitions(_ body: @escaping () -> Void) {
        var controller = rootController
        while let current = controller {
            if let coordinator = current.transitionCoordinator {
                coordinator.animate(alongsideTransition: nil) { [self] _ in afterTransitions(body) }
                return
            }
            controller = current.presentedViewController
        }
        body()
    }

    private func showContainer() {
        guard let app, let surface, container == nil else { return }
        let controller = AppContainerController(surface: surface.view, size: surface.size, navigator: self)
        container = controller
        updateIdleTimer()
        log.notice("nav: container shown \(app, privacy: .public)")
        afterTransitions { [self] in
            guard container === controller else { return } // dismissed before it could show
            rootController?.present(controller, animated: true)
        }
    }

    private func dismissContainer(_ reason: String, then: (() -> Void)? = nil) {
        guard let controller = container else {
            then?()
            return
        }
        container = nil
        updateIdleTimer()
        log.notice("nav: container dismissed \(reason, privacy: .public)")
        afterTransitions {
            // also takes down an alert ATL presented on it
            guard let presenter = controller.presentingViewController else {
                then?()
                return
            }
            presenter.dismiss(animated: true, completion: then)
        }
    }

    private func popToRoot() {
        path = NavigationPath()
        log.notice("nav: launcher root")
    }

    private func taskMoved(front: Bool, byHost: Bool) {
        // Dine's own moves updated the UI already: a late echo must not undo what the user did since
        guard !byHost, !front else { return }
        dismissContainer("back")
        popToRoot()
    }

    private func exited() {
        app = nil
        surface = nil
        keepScreenOn = false
        dismissContainer("exit")
    }

    private func updateIdleTimer() {
        UIApplication.shared.isIdleTimerDisabled = keepScreenOn && container != nil
    }

    /// notes/nav-gestures.md, pt as dp; the window starts below the status bar: nothing at its top
    func sendInsets(safeArea: UIEdgeInsets) {
        let settings = NavigationSettings.current
        func strip(_ edge: String, _ width: CGFloat) -> Float {
            let bound = ["inward", "down"].contains { (settings.bindings["\(edge).\($0)"] ?? .none) != .none }
            return bound ? Float(width) : 0
        }
        let left = strip("left", settings.stripWidth.left), right = strip("right", settings.stripWidth.right)
        let bottom = Float(safeArea.bottom)
        guard insetsSent != [left, right, bottom] else { return }
        insetsSent = [left, right, bottom]
        var insets = atl_window_insets()
        insets.system_gestures = atl_edges(left: left, top: 0, right: right, bottom: bottom)
        insets.mandatory_gestures = atl_edges(left: 0, top: 0, right: 0, bottom: bottom)
        insets.navigation_bars = atl_edges(left: 0, top: 0, right: 0, bottom: bottom)
        atl_nav_set_insets(&insets)
    }
}

/// ATL's window, with the frame its shown activity asks for: the status bar's color (nil: Dine's
/// own), whether it is light, and whether the app is fullscreen (the status bar hidden).
final class AppSurfaceView: UIView, ATLSurface {
    private(set) var frameColor: UIColor?
    private(set) var lightFrame = false
    private(set) var fullscreen = false
    var frameChanged: (@MainActor () -> Void)?

    func atlFrameChanged(_ color: UIColor?, light: Bool, fullscreen: Bool) {
        frameColor = color
        lightFrame = light
        self.fullscreen = fullscreen
        frameChanged?()
    }
}

/// The Android app's screen, presented over the launcher: ATL's window at the top left of the
/// safe area, at the size ATL was given, and its frame color behind the status bar.
final class AppContainerController: UIViewController {
    private let surface: AppSurfaceView
    private let statusBar = UIView()
    private let size: CGSize
    private unowned let navigator: Navigator
    private var edges: EdgeGestureRecognizer?

    init(surface: AppSurfaceView, size: CGSize, navigator: Navigator) {
        self.surface = surface
        self.size = size
        self.navigator = navigator
        super.init(nibName: nil, bundle: nil)
        modalPresentationStyle = .fullScreen
    }

    required init?(coder: NSCoder) {
        fatalError("not from a storyboard")
    }

    override func loadView() {
        let navigator = navigator
        view = EscapeView { navigator.back() }
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        surface.frameChanged = { [weak self] in self?.matchFrame() }
        matchFrame()
        surface.translatesAutoresizingMaskIntoConstraints = false
        statusBar.translatesAutoresizingMaskIntoConstraints = false
        view.insertSubview(surface, at: 0)
        view.insertSubview(statusBar, at: 0)
        NSLayoutConstraint.activate([
            statusBar.topAnchor.constraint(equalTo: view.topAnchor),
            statusBar.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            statusBar.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            statusBar.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            surface.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor),
            surface.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            surface.widthAnchor.constraint(equalToConstant: size.width),
            surface.heightAnchor.constraint(equalToConstant: size.height),
        ])
        let navigator = navigator
        edges = EdgeGestureRecognizer(on: view, allows: { _ in true }, perform: { navigator.perform($0) },
                                      exclusion: { navigator.exclusion })
        // edge swipes don't work under VoiceOver, and the debug agent drives the UI through these
        view.accessibilityCustomActions = [
            UIAccessibilityCustomAction(name: "Back") { _ in MainActor.assumeIsolated { navigator.back() }; return true },
            UIAccessibilityCustomAction(name: "Home") { _ in MainActor.assumeIsolated { navigator.home() }; return true },
            UIAccessibilityCustomAction(name: "Recent apps") { _ in
                MainActor.assumeIsolated { navigator.openAppsList() }
                return true
            },
        ]
    }

    override var preferredStatusBarStyle: UIStatusBarStyle {
        guard surface.frameColor != nil else { return .default }
        return surface.lightFrame ? .darkContent : .lightContent
    }

    override func viewSafeAreaInsetsDidChange() {
        super.viewSafeAreaInsetsDidChange()
        // a dismissed container leaving the window reports zero insets
        if view.window != nil {
            navigator.sendInsets(safeArea: view.safeAreaInsets)
        }
    }

    // fullscreen: Android's default cutout mode keeps the window below the notch, the strip black
    override var prefersStatusBarHidden: Bool { surface.fullscreen }

    private func matchFrame() {
        statusBar.backgroundColor = surface.fullscreen ? .black : surface.frameColor
        setNeedsStatusBarAppearanceUpdate()
        log.notice("nav: frame fullscreen \(self.surface.fullscreen)")
    }
}

/// Accessibility escape (VoiceOver's scrub, `dbg ui back`) on a view: escape searches up through
/// accessibility containers, which skip view controllers.
final class EscapeView: UIView {
    private let escape: () -> Void

    init(escape: @escaping () -> Void) {
        self.escape = escape
        super.init(frame: .zero)
    }

    required init?(coder: NSCoder) {
        fatalError("not from a storyboard")
    }

    override func accessibilityPerformEscape() -> Bool {
        escape()
        return true
    }
}

/// The running apps list: a placeholder until there is more than one app to list.
final class AppsListController: UIViewController, UIAdaptivePresentationControllerDelegate {
    private unowned let navigator: Navigator
    private let appRuns: Bool

    init(navigator: Navigator, appRuns: Bool) {
        self.navigator = navigator
        self.appRuns = appRuns
        super.init(nibName: nil, bundle: nil)
        modalPresentationStyle = .pageSheet
    }

    required init?(coder: NSCoder) {
        fatalError("not from a storyboard")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemOrange
        presentationController?.delegate = self

        let label = UILabel()
        label.text = "Running apps\nunder construction"
        label.numberOfLines = 0
        label.textAlignment = .center
        label.font = .preferredFont(forTextStyle: .title2)

        let button = UIButton(configuration: .filled(), primaryAction: UIAction(title: "back to app") { [unowned self] _ in
            navigator.backToApp()
        })
        button.isEnabled = appRuns

        let stack = UIStackView(arrangedSubviews: [label, button])
        stack.axis = .vertical
        stack.spacing = 24
        stack.alignment = .center
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: view.centerYAnchor),
        ])
    }

    func presentationControllerDidDismiss(_ presentationController: UIPresentationController) {
        navigator.appsListSwipedAway()
    }
}

extension EdgeExclusion {
    init(_ exclusion: atl_gesture_exclusion) {
        var exclusion = exclusion
        func spans<T>(_ tuple: inout T, _ count: Int32) -> [ClosedRange<CGFloat>] {
            withUnsafeBytes(of: &tuple) { bytes in
                bytes.bindMemory(to: atl_span.self).prefix(Int(count)).map { CGFloat($0.top)...CGFloat($0.bottom) }
            }
        }
        left = spans(&exclusion.left, exclusion.left_count)
        right = spans(&exclusion.right, exclusion.right_count)
    }
}
