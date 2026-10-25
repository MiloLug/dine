# Inlined constants escape the incremental hax.jar build (2026-10-25)

dine-atl's incremental Java build doesn't recompile a class whose only link to another class is a
compile-time constant it reads from it. The class then keeps the constant's old value in its
bytecode, and, if it has native methods, in its JNI header. Untested: this follows from how the two
tools work, no repro was run and no real case is known.

## Cause

- With ant installed, meson builds hax.jar through `src/api-impl/build.xml`. Its
  `<depend closure="true">` deletes the class files of every class that depends, directly or
  transitively, on a changed class, and javac recompiles them.
- `<depend>` takes dependencies from the `Class` entries in each class file's constant pool (read
  from ant 1.10.18's `ClassFile.getClassRefs`).
- javac inlines compile-time constants (`static final` primitives and Strings with a constant
  initializer) and records no reference to the class that declares them. A class that uses only
  `Other.Y` from `Other` has no `Class` entry for `Other`, so `<depend>` never links the two.

## Shape

```java
// A.java
public class A { public static final int Y = 1; }

// B.java: no other use of A
public class B { static final int X = A.Y; native void f(); }
```

Change `A.Y` to 2 and run an incremental build: A recompiles, B doesn't. `B.class` and
`B.h` (`#define B_X 1L`) keep 1.

A class that uses `A` in any other way (a method call, a field of type `A`, `extends A`) has the
`Class` entry and recompiles. View's `LAYOUT_DIRECTION_* = LayoutDirection.*` constants don't hit
the bug for that reason: the ant dependency cache lists `LayoutDirection` as a dependency of View.

## Not affected

- A build dir with no compiled classes yet (fresh `meson setup`, a deleted `hax.jar.p`): javac
  compiles every source.
- The meson `jar()` path, used when ant isn't installed: one javac run over all sources on every
  change.

## Workaround and fix

- After changing the value of a constant that other classes read, delete
  `out/linux/build/dine-atl/src/api-impl/hax.jar.p` and
  `out/linux/build/dine-atl-headless/src/api-impl/hax.jar.p`, then build. Untested.
- A full javac on every Java edit closes the gap: 5.0 s against 1.36 s for a leaf class and 4.06 s
  for View with closure (scratch runs of the hax build), and every edit then rewrites all 83 headers
  and recompiles the C files that include them.
