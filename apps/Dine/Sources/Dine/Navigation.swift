import CArtBridge
import OSLog
import SwiftUI
import UIKit

private let log = Logger(subsystem: "dev.dine.Dine", category: "art")

/// Back, Home, the app's container and the running apps list (notes/nav-gestures.md) for the apps
/// ATL runs, one container shown at a time. Dine's UI changes first, then ATL hears: Home never
/// waits for Java.
@MainActor
final class Navigator: ObservableObject {
    @Published var path = NavigationPath()

    /// An app ATL runs in Dine's VM.
    private struct RunningApp {
        let name: String
        let apk: String  // its package starts once per VM: a second tap brings it to front
        let handle: OpaquePointer  // ATL's (dine_atl_app_new), which nav calls take
        var surface: (view: AppSurfaceView, size: CGSize)  // its window, at its current size
        var keepScreenOn = false  // the app asks; it applies while its container shows
        var exclusion = EdgeExclusion()  // its shown activity's
        var safeArea = UIEdgeInsets.zero  // its container's
        var ime: Float = 0  // the keyboard's overlap with its window, while it is in front
        var statusTop: Float = 0  // the status bar's height while its window runs under it
        var insetsSent: [Float] = []
    }

    private var apps: [RunningApp] = []
    private var current: OpaquePointer?  // the app the container, Back and Home act on
    private var container: AppContainerController?
    private var appsList: AppsListController?
    private var listReturnsToApp = false
    private var listener = atl_embedded_listener()

    private var currentIndex: Int? { apps.firstIndex { $0.handle == current } }
    private var app: String? { currentIndex.map { apps[$0].name } }
    private var handle: OpaquePointer? { currentIndex.map { apps[$0].handle } }
    private var surface: (view: AppSurfaceView, size: CGSize)? { currentIndex.map { apps[$0].surface } }
    private var keepScreenOn: Bool { currentIndex.map { apps[$0].keepScreenOn } ?? false }
    var exclusion: EdgeExclusion { currentIndex.map { apps[$0].exclusion } ?? EdgeExclusion() }
    private var launcherEdges: EdgeGestureRecognizer?
    private var watchesStyle = false

    init() {
        // the navigator lives as long as the app (DineMain's state object)
        listener.context = Unmanaged.passUnretained(self).toOpaque()
        listener.task_moved = { context, app, front, byHost in
            let navigator = Unmanaged<Navigator>.fromOpaque(context!).takeUnretainedValue()
            DispatchQueue.main.async { MainActor.assumeIsolated { navigator.taskMoved(app, front: front, byHost: byHost) } }
        }
        listener.exited = { context, app, _ in
            let navigator = Unmanaged<Navigator>.fromOpaque(context!).takeUnretainedValue()
            DispatchQueue.main.async { MainActor.assumeIsolated { navigator.exited(app) } }
        }
        listener.exclusion_changed = { context, app, exclusion in
            let navigator = Unmanaged<Navigator>.fromOpaque(context!).takeUnretainedValue()
            let spans = EdgeExclusion(exclusion!.pointee)
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    navigator.update(app) { $0.exclusion = spans }
                    log.notice("nav: exclusion left \(spans.left.count) right \(spans.right.count)")
                }
            }
        }
        listener.keep_screen_on = { context, app, on in
            let navigator = Unmanaged<Navigator>.fromOpaque(context!).takeUnretainedValue()
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    navigator.update(app) { $0.keepScreenOn = on }
                    navigator.updateIdleTimer()
                    log.notice("nav: keep screen on \(on)")
                }
            }
        }
    }

    /// `start` runs ATL with the app's window and the listener; on success the app's container
    /// comes up. An `apk` that runs already comes to the front instead.
    func run(_ app: String, apk: String, start: (UnsafePointer<dine_atl_window>, UnsafePointer<atl_embedded_listener>, OpaquePointer) -> Int32) {
        if let running = apps.first(where: { $0.apk == apk }) {
            current = running.handle
            log.notice("nav: \(app, privacy: .public) runs already: front")
            front()
            return
        }
        guard let keyWindow = rootController?.view.window else {
            return log.error("atl: no key window to size the app's window from")
        }
        // below the status bar to the screen's bottom: the app gets the home indicator as insets
        let safeArea = keyWindow.safeAreaLayoutGuide.layoutFrame
        let size = CGSize(width: safeArea.width, height: keyWindow.bounds.maxY - safeArea.minY)
        let traits = keyWindow.traitCollection
        let scale = traits.displayScale
        let view = AppSurfaceView()
        let night = Self.night(traits)
        if !watchesStyle {
            // the key window: the launcher's view leaves it under a full-screen container
            watchesStyle = true
            keyWindow.registerForTraitChanges([UITraitUserInterfaceStyle.self]) { [weak self] (window: UIWindow, _: UITraitCollection) in
                self?.styleChanged(window.traitCollection)
            }
        }
        let handle = dine_atl_app_new()!
        let whole = Self.whole(size, scale: scale)
        let window = dine_atl_window(view: Unmanaged.passUnretained(view).toOpaque(),
                                     width: Int32(whole.width * scale), height: Int32(whole.height * scale),
                                     density_dpi: Int32((160 * scale).rounded()), night: night)
        let previous = current
        apps.append(RunningApp(name: app, apk: apk, handle: handle, surface: (view, whole)))
        current = handle
        sendInsets(safeArea: keyWindow.safeAreaInsets)
        let started = withUnsafePointer(to: window) { window in
            withUnsafePointer(to: listener) { start(window, $0, handle) }
        }
        guard started == 0 else {
            apps.removeAll { $0.handle == handle }
            current = previous
            return
        }
        showContainer()
    }

    func back() {
        guard let handle else { return }
        _ = atl_nav_back(handle)
    }

    func home() {
        guard container != nil else { return }
        dismissContainer("home")
        popToRoot()
        if let handle {
            _ = atl_nav_home(handle)
        }
    }

    /// From the app it moves the app to the back; dismissing the list brings it back.
    func openAppsList() {
        guard appsList == nil else { return }
        listReturnsToApp = container != nil
        if listReturnsToApp, let handle {
            _ = atl_nav_home(handle)
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
        guard app != nil, let handle else { return }
        _ = atl_nav_front(handle)
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
        keyboardChanged(overlap: 0) // the keyboard stays with the app in front
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

    /// A window size in pt that is whole px, as ATL's window is.
    static func whole(_ size: CGSize, scale: CGFloat) -> CGSize {
        CGSize(width: (size.width * scale).rounded(.down) / scale, height: (size.height * scale).rounded(.down) / scale)
    }

    private static func night(_ traits: UITraitCollection) -> Int32 {
        switch traits.userInterfaceStyle {
        case .dark: 0x20  // Configuration.UI_MODE_NIGHT_YES
        case .light: 0x10
        default: 0
        }
    }

    // every running app, also those in the back
    private func styleChanged(_ traits: UITraitCollection) {
        let night = Self.night(traits)
        for app in apps {
            atl_nav_set_night(app.handle, night)
        }
        log.notice("nav: night \(night)")
    }

    private func update(_ app: OpaquePointer?, _ change: (inout RunningApp) -> Void) {
        guard let i = apps.firstIndex(where: { $0.handle == app }) else { return }
        change(&apps[i])
    }

    private func taskMoved(_ app: OpaquePointer?, front: Bool, byHost: Bool) {
        // Dine's own moves updated the UI already: a late echo must not undo what the user did since
        guard app == current, !byHost, !front else { return }
        dismissContainer("back")
        popToRoot()
    }

    private func exited(_ app: OpaquePointer?) {
        apps.removeAll { $0.handle == app }
        guard app == current else { return }
        current = nil
        dismissContainer("exit")
    }

    private func updateIdleTimer() {
        UIApplication.shared.isIdleTimerDisabled = keepScreenOn && container != nil
    }

    /// The keyboard's overlap with the shown app's window, pt.
    func keyboardChanged(overlap: CGFloat) {
        guard let index = currentIndex else { return }
        apps[index].ime = Float(overlap)
        sendInsets(index)
    }

    func sendInsets(safeArea: UIEdgeInsets) {
        guard let index = currentIndex else { return }
        apps[index].safeArea = safeArea
        sendInsets(index)
    }

    /// The app's window moved under the status bar or back: its size first, then its insets, so
    /// its next layout has both.
    func windowChanged(_ surface: AppSurfaceView, size: CGSize, statusTop: CGFloat) {
        guard let index = apps.firstIndex(where: { $0.surface.view === surface }) else { return }
        if apps[index].surface.size != size {
            apps[index].surface.size = size
            atl_nav_set_window_size(apps[index].handle, Float(size.width), Float(size.height))
            log.notice("nav: window size \(Int(size.width))x\(Int(size.height))")
        }
        apps[index].statusTop = Float(statusTop)
        sendInsets(index)
    }

    /// notes/nav-gestures.md, pt as dp; at its top only the status bar while the window runs under it
    private func sendInsets(_ index: Int) {
        let handle = apps[index].handle
        let safeArea = apps[index].safeArea, ime = apps[index].ime, statusTop = apps[index].statusTop
        let settings = NavigationSettings.current
        func strip(_ edge: String, _ width: CGFloat) -> Float {
            let bound = ["inward", "down"].contains { (settings.bindings["\(edge).\($0)"] ?? .none) != .none }
            return bound ? Float(width) : 0
        }
        let left = strip("left", settings.stripWidth.left), right = strip("right", settings.stripWidth.right)
        let bottom = Float(safeArea.bottom)
        guard apps[index].insetsSent != [left, right, bottom, ime, statusTop] else { return }
        apps[index].insetsSent = [left, right, bottom, ime, statusTop]
        var insets = atl_window_insets()
        insets.system_gestures = atl_edges(left: left, top: 0, right: right, bottom: bottom)
        insets.mandatory_gestures = atl_edges(left: 0, top: 0, right: 0, bottom: bottom)
        insets.navigation_bars = atl_edges(left: 0, top: 0, right: 0, bottom: bottom)
        insets.status_bars = atl_edges(left: 0, top: statusTop, right: 0, bottom: 0)
        insets.ime = atl_edges(left: 0, top: 0, right: 0, bottom: ime)
        atl_nav_set_insets(handle, &insets)
    }
}

/// ATL's window, with the frame its shown activity asks for (ATLSurface): the status bar's color
/// (nil: Dine's own), whether it is light, the status bar hidden, the window under it, the home
/// indicator hidden, and immersive edges.
final class AppSurfaceView: UIView, ATLSurface {
    private(set) var frameColor: UIColor?
    private(set) var lightFrame = false
    private(set) var fullscreen = false
    private(set) var coverTop = false
    private(set) var hideNavigation = false
    private(set) var immersive = false
    private(set) var dim: CGFloat = 0
    var frameChanged: (@MainActor () -> Void)?

    func atlFrameChanged(_ color: UIColor?, light: Bool, fullscreen: Bool, coverTop: Bool, hideNavigation: Bool, immersive: Bool) {
        frameColor = color
        lightFrame = light
        self.fullscreen = fullscreen
        self.coverTop = coverTop
        self.hideNavigation = hideNavigation
        self.immersive = immersive
        frameChanged?()
    }

    func atlDimChanged(_ amount: CGFloat) {
        dim = amount
        frameChanged?()
    }
}

/// The Android app's screen, presented over the launcher: ATL's window at the top left of the
/// safe area, or at the screen's top while it runs under the status bar, and its frame color
/// behind the status bar.
final class AppContainerController: UIViewController {
    private let surface: AppSurfaceView
    private let statusBar = UIView()
    private let statusDim: UIView = { // a dialog's dim over the status bar
        let dim = UIView()
        dim.alpha = 0
        return dim
    }()
    private let size: CGSize
    private unowned let navigator: Navigator
    private var edges: EdgeGestureRecognizer?
    private var surfaceTop: NSLayoutConstraint?
    private var surfaceSize: (width: NSLayoutConstraint, height: NSLayoutConstraint)?
    private var coversTop = false

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
        statusDim.translatesAutoresizingMaskIntoConstraints = false
        statusDim.backgroundColor = .black
        statusDim.isUserInteractionEnabled = false
        view.insertSubview(surface, at: 0)
        view.insertSubview(statusDim, at: 0)
        view.insertSubview(statusBar, at: 0)
        NSLayoutConstraint.activate([
            statusBar.topAnchor.constraint(equalTo: view.topAnchor),
            statusBar.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            statusBar.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            statusBar.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            statusDim.topAnchor.constraint(equalTo: statusBar.topAnchor),
            statusDim.leadingAnchor.constraint(equalTo: statusBar.leadingAnchor),
            statusDim.trailingAnchor.constraint(equalTo: statusBar.trailingAnchor),
            statusDim.bottomAnchor.constraint(equalTo: statusBar.bottomAnchor),
            surface.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor),
        ])
        let width = surface.widthAnchor.constraint(equalToConstant: size.width)
        let height = surface.heightAnchor.constraint(equalToConstant: size.height)
        surfaceSize = (width, height)
        NSLayoutConstraint.activate([width, height])
        coversTop = surface.coverTop
        pinSurfaceTop()
        let navigator = navigator, surface = surface
        edges = EdgeGestureRecognizer(on: view, allows: { _ in true }, perform: { navigator.perform($0) },
                                      exclusion: { navigator.exclusion }, windowTop: { surface.frame.minY })
        for name in [UIResponder.keyboardWillChangeFrameNotification, UIResponder.keyboardWillHideNotification] {
            NotificationCenter.default.addObserver(self, selector: #selector(keyboardWillChange(_:)), name: name, object: nil)
        }
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
        guard surface.frameColor != nil || surface.coverTop else { return .default }
        return surface.lightFrame ? .darkContent : .lightContent
    }

    override func viewSafeAreaInsetsDidChange() {
        super.viewSafeAreaInsetsDidChange()
        // a dismissed container leaving the window reports zero insets
        if view.window != nil {
            navigator.sendInsets(safeArea: view.safeAreaInsets)
            resizeWindow()
        }
    }

    // immersive: the bottom deferral alone hides the indicator; hiding it too lets the first swipe through (iOS 27)
    override var prefersHomeIndicatorAutoHidden: Bool { surface.hideNavigation && !surface.immersive }

    // immersive: a first swipe at a hidden bar's edge only reveals the system's own
    override var preferredScreenEdgesDeferringSystemGestures: UIRectEdge {
        guard surface.immersive else { return [] }
        var edges: UIRectEdge = []
        if surface.hideNavigation { edges.insert(.bottom) }
        if surface.fullscreen { edges.insert(.top) }
        return edges
    }

    private func pinSurfaceTop() {
        surfaceTop?.isActive = false
        surfaceTop = surface.topAnchor.constraint(equalTo: coversTop ? view.topAnchor : view.safeAreaLayoutGuide.topAnchor)
        surfaceTop?.isActive = true
    }

    // the window's safe area, as run() sizes it: the view's is 0 during the present animation
    private func resizeWindow() {
        guard let window = view.window, let surfaceSize else { return }
        let safeArea = window.safeAreaInsets
        let top = coversTop ? 0 : safeArea.top
        let size = Navigator.whole(CGSize(width: window.bounds.width - safeArea.left - safeArea.right, height: window.bounds.height - top),
                                   scale: window.traitCollection.displayScale)
        surfaceSize.width.constant = size.width
        surfaceSize.height.constant = size.height
        navigator.windowChanged(surface, size: size, statusTop: coversTop ? safeArea.top : 0)
    }

    // the end frame's overlap with the app's window: its IME inset
    @objc private func keyboardWillChange(_ note: Notification) {
        guard let screen = view.window?.screen, let end = note.userInfo?[UIResponder.keyboardFrameEndUserInfoKey] as? CGRect else { return }
        let keyboard = surface.convert(end, from: screen.coordinateSpace)
        let overlap = note.name == UIResponder.keyboardWillHideNotification ? 0 : surface.bounds.maxY - keyboard.minY
        navigator.keyboardChanged(overlap: min(max(overlap, 0), surface.bounds.height))
    }

    // fullscreen: Android's default cutout mode keeps the window below the notch, the strip black
    override var prefersStatusBarHidden: Bool { surface.fullscreen }

    private func matchFrame() {
        if coversTop != surface.coverTop, surfaceSize != nil {
            coversTop = surface.coverTop
            pinSurfaceTop()
            resizeWindow()
        }
        setNeedsUpdateOfHomeIndicatorAutoHidden()
        setNeedsUpdateOfScreenEdgesDeferringSystemGestures()
        statusBar.backgroundColor = surface.fullscreen ? .black : surface.frameColor
        if statusDim.alpha != surface.dim {
            statusDim.alpha = surface.dim
            log.notice("nav: status dim \(Double(self.surface.dim), format: .fixed(precision: 2), privacy: .public)")
        }
        setNeedsStatusBarAppearanceUpdate()
        log.notice("nav: frame fullscreen \(self.surface.fullscreen) cover \(self.surface.coverTop) hide navigation \(self.surface.hideNavigation) immersive \(self.surface.immersive)")
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
