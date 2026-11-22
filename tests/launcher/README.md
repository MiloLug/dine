# Launcher tests

- `edge_gesture_test.swift`: the edge swipe classifier (`apps/Dine/Sources/Dine/EdgeGesture.swift`:
  strips, exclusion spans, axis, bindings, commit distances and speed). `tools/dine test unit`
  compiles both files with swiftc for this machine and runs the result
  (`tools/py/dine/test_edge_gesture.py`), so `EdgeGesture.swift` imports no UIKit.

The app grid, the library database and the settings have no test yet
([DINE-15](../../notes/general-todo.md#dine-15)).
