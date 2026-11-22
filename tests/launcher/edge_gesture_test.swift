// Compiled with apps/Dine/Sources/Dine/EdgeGesture.swift by tools/py/dine/test_edge_gesture.py.
import Foundation

typealias Edge = EdgeGesture.Edge
typealias Axis = EdgeGesture.Axis

let settings = NavigationSettings()
// a 390x844 pt screen; the safe area is 47 to 810
let screen = CGRect(x: 0, y: 0, width: 390, height: 844)

@main
struct EdgeGestureTest {
    static func main() {
        var failures = 0
        func expect<T: Equatable>(_ what: String, _ got: T, _ want: T) {
            guard got != want else { return }
            print("FAIL \(what): \(got), want \(want)")
            failures += 1
        }
        func edge(_ x: CGFloat, _ y: CGFloat, windowTop: CGFloat = 47, _ exclusion: EdgeExclusion = EdgeExclusion()) -> Edge? {
            EdgeGesture.edge(at: CGPoint(x: x, y: y), in: screen, safeTop: 47, safeBottom: 34, windowTop: windowTop,
                             settings: settings, exclusion: exclusion)
        }

        expect("left strip", edge(20, 400), Edge.left)
        expect("past the left strip", edge(21, 400), nil)
        expect("right strip", edge(370, 400), Edge.right)
        expect("before the right strip", edge(369, 400), nil)
        expect("above the safe area", edge(5, 46), nil)
        expect("the safe area's top", edge(5, 47), Edge.left)
        expect("the safe area's bottom", edge(385, 810), Edge.right)
        expect("below the safe area", edge(385, 811), nil)

        let right = EdgeExclusion(left: [], right: [200...300])
        expect("the span counts from the window's top", edge(385, 247, right), nil)
        expect("the span's end", edge(385, 347, right), nil)
        expect("over the span", edge(385, 246, right), Edge.right)
        expect("under the span", edge(385, 348, right), Edge.right)
        expect("the other edge in the span", edge(5, 300, right), Edge.left)
        expect("a window at the screen's top", edge(385, 200, windowTop: 0, right), nil)
        expect("under it there", edge(385, 301, windowTop: 0, right), Edge.right)
        let left = EdgeExclusion(left: [100...120, 400...420], right: [])
        expect("a left span", edge(5, 157, left), nil)
        expect("a second left span", edge(5, 457, left), nil)
        expect("between the spans", edge(5, 300, left), Edge.left)
        expect("the right edge beside a left span", edge(385, 157, left), Edge.right)

        func axis(_ edge: Edge, _ x: CGFloat, _ y: CGFloat, speed: CGPoint = .zero) -> Axis? {
            EdgeGesture.axis(edge: edge, translation: CGPoint(x: x, y: y), velocity: speed)
        }
        expect("left inward", axis(.left, 12, 3), Axis.inward)
        expect("left outward", axis(.left, -12, 3), nil)
        expect("right inward", axis(.right, -12, 3), Axis.inward)
        expect("right outward", axis(.right, 12, 3), nil)
        expect("down", axis(.left, 3, 12), Axis.down)
        expect("up", axis(.right, 3, -12), nil)
        expect("a diagonal", axis(.left, 10, 10), Axis.inward)
        expect("no move yet", axis(.right, 0, 0, speed: CGPoint(x: -90, y: 10)), Axis.inward)

        expect("left inward's action", EdgeGesture.action(edge: .left, axis: .inward, settings: settings), NavAction.appsList)
        expect("left down's action", EdgeGesture.action(edge: .left, axis: .down, settings: settings), NavAction.home)
        expect("right inward's action", EdgeGesture.action(edge: .right, axis: .inward, settings: settings), NavAction.back)
        expect("right down's action", EdgeGesture.action(edge: .right, axis: .down, settings: settings), NavAction.none)

        func progress(_ edge: Edge, _ axis: Axis) -> [CGFloat] {
            let (travel, speed) = EdgeGesture.progress(edge: edge, axis: axis, translation: CGPoint(x: 30, y: 70),
                                                       velocity: CGPoint(x: 300, y: 700))
            return [travel, speed]
        }
        expect("left inward's progress", progress(.left, .inward), [30, 300])
        expect("right inward's progress", progress(.right, .inward), [-30, -300])
        expect("down's progress", progress(.right, .down), [70, 700])

        func commits(_ axis: Axis, _ travel: CGFloat, _ speed: CGFloat = 0) -> Bool {
            EdgeGesture.commits(axis: axis, travel: travel, speed: speed, settings: settings)
        }
        expect("47 pt inward", commits(.inward, 47), false)
        expect("48 pt inward", commits(.inward, 48), true)
        expect("95 pt down", commits(.down, 95), false)
        expect("96 pt down", commits(.down, 96), true)
        expect("599 pt/s", commits(.inward, 5, 599), false)
        expect("600 pt/s", commits(.inward, 5, 600), true)

        if failures > 0 { exit(1) }
        print("edge gestures ok")
    }
}
