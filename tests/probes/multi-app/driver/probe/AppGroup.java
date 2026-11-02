package probe;

import java.util.concurrent.ConcurrentLinkedQueue;

/** One app's threads. Keeps uncaught exceptions as strings: a Throwable's trace pins the app's classes. */
final class AppGroup extends ThreadGroup {
    final ConcurrentLinkedQueue<String> uncaught = new ConcurrentLinkedQueue<>();

    AppGroup(String name) { super(name); }

    @Override public void uncaughtException(Thread t, Throwable e) {
        Throwable cause = e.getCause();
        uncaught.add(t.getName() + ":" + e.getClass().getName()
                + (cause != null ? "(" + cause.getClass().getName() + ")" : ""));
    }
}
