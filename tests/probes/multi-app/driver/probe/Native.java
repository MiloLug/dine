package probe;

/** libprobe.so (native/probe.cc). */
final class Native {
    static { System.loadLibrary("probe"); }

    /** "ok", or the layout checks that failed; {@code self} must be the calling thread. */
    static native String check(Thread self);

    /**
     * 0 delivered, 1 still starting, 2 not alive, 3 the thread died during the checkpoint.
     * {@code unpark} also wakes a {@code LockSupport.park}.
     */
    static native int inject(Thread t, Throwable exception, boolean unpark);

    /** The suspended art::Thread for {@link #resume}, or -1 on a timeout. */
    static native long suspend(Thread t);

    static native boolean resume(long thread);

    static native String dumpThreads();

    /** The owner's thin lock id; 0 when nobody holds the monitor. */
    static native int lockOwner(Object o);

    /** {bytes, objects, walk micros} of the objects whose class {@code loader} defined. */
    static native long[] heapForLoader(ClassLoader loader);

    /** A C thread attached into {@code group} that calls static {@code method()V} of {@code cls} in a loop. */
    static native void startNativeCaller(ThreadGroup group, Class<?> cls, String method, boolean careless);
}
