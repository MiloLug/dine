package probe;

import android.system.Os;
import android.system.OsConstants;
import dalvik.system.DexFile;
import dalvik.system.PathClassLoader;
import dalvik.system.VMDebug;
import dalvik.system.VMRuntime;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileDescriptor;
import java.io.FileReader;
import java.lang.ref.WeakReference;
import java.net.Socket;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * The system side of the multi-app probes: two apps in one VM, each with its own loader and thread
 * group. Modes: {@code check}, {@code case <kind>} (stopping a thread), {@code drop <plain|leak> <n>}.
 */
public final class Driver {
    static final String DIR = System.getProperty("probe.dir");

    static final class App {
        final String name;
        final PathClassLoader loader;
        final AppGroup group;

        App(String name) {
            this.name = name;
            // probe.extrajar: another dex on app b's path, to see what a real app's dex leaves behind
            String extra = name.equals("b") ? System.getProperty("probe.extrajar", "") : "";
            loader = new PathClassLoader(DIR + "/app-" + name + ".jar" + (extra.isEmpty() ? "" : ":" + extra),
                    String.class.getClassLoader());
            group = new AppGroup("app-" + name);
        }
    }

    public static void main(String[] args) throws Exception {
        switch (args[0]) {
            case "check":
                out("check", Native.check(Thread.currentThread()) + " threads=" + threadCount());
                break;
            case "case":
                runCase(args[1]);
                break;
            case "drop":
                drop(args[1], Integer.parseInt(args[2]));
                break;
            default:
                throw new IllegalArgumentException(args[0]);
        }
        System.out.flush();
        System.exit(0);
    }

    static void runCase(String kind) throws Exception {
        App a = new App("a");
        App b = new App("b");
        call(a, "heartbeat");
        Thread.sleep(50);
        int base = threadCount();
        String bKind = kind.startsWith("read") ? "read" : kind.startsWith("storm") ? "storm"
                : kind.replace("-unpark", "").replace("-fresh", "");
        CountDownLatch ready = new CountDownLatch(1);
        List<Object> sockets = new CopyOnWriteArrayList<>();
        Object extra = null;
        if (kind.equals("blocked")) {
            CountDownLatch holding = new CountDownLatch(1);
            extra = call(a, "hold", holding);
            holding.await();
        } else if (bKind.equals("storm")) {
            extra = bootClasses();
        }
        if (kind.equals("juclock")) {
            juclock("case juclock", b);
            return;
        }
        String worker;
        if (kind.startsWith("native")) {
            Native.startNativeCaller(b.group, Class.forName("app.App", true, b.loader), "blockingCall",
                    kind.equals("native-careless"));
            while (!(Boolean) call(b, "nativeIn")) Thread.sleep(10);
            worker = "b-native";
        } else {
            call(b, "start", bKind, ready, extra, sockets);
            if (!ready.await(10, TimeUnit.SECONDS)) throw new IllegalStateException("not ready");
            worker = "b-" + bKind;
        }
        Thread.sleep(200);
        Thread w = find(b.group, worker);
        String tag = "case " + kind;
        out(tag, "state-before=" + w.getState());
        long beats = beats(a);
        // "-fresh": no interrupt-only control, so the thread's interrupt flag is clear at injection
        boolean blocking = kind.matches("wait|park.*|sleep|read-.*|native-.*") && !kind.endsWith("-fresh");
        if (blocking) {
            w.interrupt();
            Thread.sleep(300);
            out(tag, "interrupt-only alive=" + w.isAlive() + " state=" + w.getState());
        }
        switch (kind) {
            case "catchall": catchall(tag, w); break;
            case "blocked": blocked(tag, a, b, w); break;
            case "frozen": frozen(tag, a, b, w); break;
            case "clinit": clinit(tag, b, w); break;
            case "storm": storm(tag, b, w, (String[]) extra, sockets, true); break;
            case "storm-control": storm(tag, b, w, (String[]) extra, sockets, false); break;
            default: {
                long t0 = System.nanoTime();
                int r = Native.inject(w, new ThreadDeath(), kind.endsWith("-unpark"));
                w.interrupt();
                FileDescriptor fd = null;
                Socket socket = null;
                for (Object s : sockets) {
                    if (s instanceof FileDescriptor) fd = (FileDescriptor) s;
                    if (s instanceof Socket) socket = (Socket) s;
                }
                if (kind.equals("read-shutdown")) Os.shutdown(fd, OsConstants.SHUT_RDWR);
                if (kind.equals("read-close")) socket.close();
                if (kind.equals("read-rawclose")) Os.close(fd);
                w.join(2000);
                out(tag, "inject=" + r + " stopped=" + !w.isAlive() + " ms=" + (System.nanoTime() - t0) / 1_000_000
                        + " state=" + w.getState());
            }
        }
        Thread.sleep(200);
        if (kind.equals("wait") || kind.equals("frozen")) {
            out(tag, "lock-owner=" + Native.lockOwner(call(b, "lock")));
        }
        out(tag, "uncaught=" + b.group.uncaught + " threads=" + threadCount() + " baseline=" + base
                + " heartbeat-advancing=" + (beats(a) > beats));
    }

    /** A shared lock taken in try/finally by an app thread: how often an injection leaves it held. */
    static void juclock(String tag, App b) throws Exception {
        int trials = 50;
        int held = 0;
        for (int i = 0; i < trials; i++) {
            java.util.concurrent.locks.ReentrantLock lock = new java.util.concurrent.locks.ReentrantLock();
            CountDownLatch ready = new CountDownLatch(1);
            call(b, "start", "juclock", ready, lock, new CopyOnWriteArrayList<>());
            ready.await();
            Thread w = find(b.group, "b-juclock");
            Thread.sleep(5);
            Native.inject(w, new ThreadDeath(), false);
            w.join(1000);
            if (w.isAlive()) throw new IllegalStateException("juclock worker still running");
            if (lock.isLocked()) held++;
        }
        out(tag, "trials=" + trials + " lock-left-held=" + held);
    }

    static void catchall(String tag, Thread w) throws Exception {
        for (int i = 1; i <= 5; i++) {
            Native.inject(w, new ThreadDeath(), false);
            w.interrupt();
            w.join(300);
            if (!w.isAlive()) {
                out(tag, "stopped after injections=" + i);
                return;
            }
        }
        out(tag, "stopped=false after injections=5 state=" + w.getState());
    }

    static void blocked(String tag, App a, App b, Thread w) throws Exception {
        int r = Native.inject(w, new ThreadDeath(), false);
        w.interrupt();
        w.join(1000);
        out(tag, "inject=" + r + " stopped-while-held=" + !w.isAlive() + " state=" + w.getState());
        call(a, "release");
        w.join(2000);
        out(tag, "stopped-after-release=" + !w.isAlive() + " b-entered=" + call(b, "entered"));
    }

    static void frozen(String tag, App a, App b, Thread w) throws Exception {
        long t = Native.suspend(w);
        out(tag, "suspended=" + (t != 0 && t != -1));
        call(a, "enter", call(b, "lock"));
        Thread.sleep(300);
        out(tag, "contender-entered-while-frozen=" + call(a, "entered"));
        int r = Native.inject(w, new ThreadDeath(), false);
        Thread.sleep(500);
        out(tag, "inject=" + r + " alive-while-frozen=" + w.isAlive());
        boolean resumed = Native.resume(t);
        w.join(2000);
        Thread.sleep(200);
        out(tag, "resume=" + resumed + " stopped-after-resume=" + !w.isAlive()
                + " contender-entered=" + call(a, "entered"));
    }

    static void clinit(String tag, App b, Thread w) throws Exception {
        String[] result = new String[1];
        Thread system = new Thread(() -> result[0] = initOutcome("app.Slow", b.loader), "system-waiter");
        system.start();
        Thread.sleep(200);
        out(tag, "system-waiter-state=" + system.getState());
        int r = Native.inject(w, new ThreadDeath(), false);
        w.interrupt();
        w.join(2000);
        system.join(2000);
        Thread.sleep(200);
        out(tag, "inject=" + r + " initializer-stopped=" + !w.isAlive() + " system-waiter=" + result[0]
                + " reinit=" + initOutcome("app.Slow", b.loader));
    }

    static void storm(String tag, App b, Thread w, String[] classes, List<Object> hits, boolean inject)
            throws Exception {
        int injections = 0;
        int restarts = 0;
        long t0 = System.nanoTime();
        while (true) {
            if (System.nanoTime() - t0 > 60_000_000_000L) {
                out(tag, "deadline: index=" + call(b, "stormIndex") + " state=" + w.getState()
                        + " system-properties-lock-owner=" + Native.lockOwner(System.getProperties()));
                for (StackTraceElement frame : w.getStackTrace()) out(tag, "  at " + frame);
                System.out.println(Native.dumpThreads());
                break;
            }
            if (!w.isAlive()) {
                if ((Integer) call(b, "stormIndex") >= classes.length) break;
                restarts++;
                call(b, "start", "storm", new CountDownLatch(1), classes, hits);
                // a restarted worker near the end of the list may finish before this looks for it
                Thread next = findOrNull(b.group, "b-storm");
                if (next != null) w = next;
                continue;
            }
            if (inject && Native.inject(w, new Marker(), false) == 0) injections++;
            Thread.sleep(1);
        }
        out(tag, "classes=" + classes.length + " injections=" + injections + " restarts=" + restarts + " ms="
                + (System.nanoTime() - t0) / 1_000_000 + " hits=" + hits.size());
        int poisoned = 0;
        for (Object hit : hits) {
            String outcome = initOutcome((String) hit, null);
            if (!outcome.equals("ok")) poisoned++;
            out(tag, "hit " + hit + " reinit=" + outcome);
        }
        out(tag, "poisoned=" + poisoned);
    }

    static void drop(String variant, int cycles) throws Exception {
        String tag = "drop " + variant;
        App a = new App("a");
        call(a, "heartbeat");
        collect(null);
        out(tag, "baseline " + metrics());
        for (int i = 1; i <= cycles; i++) {
            WeakReference<ClassLoader> loader = loadAndDrop(tag, variant, i);
            int clearedAt = collect(loader);
            out(tag, "cycle=" + i + " loader-cleared-at-gc=" + clearedAt + " " + metrics());
        }
        long beats = beats(a);
        Thread.sleep(100);
        out(tag, "heartbeat-advancing=" + (beats(a) > beats));
        for (String fd : new File("/proc/self/fd").list()) {
            try {
                out(tag, "fd " + fd + " " + Os.readlink("/proc/self/fd/" + fd));
            } catch (Exception e) {
                out(tag, "fd " + fd + " " + e);
            }
        }
    }

    /** Loads app b, runs it, drops it; returns once nothing on this frame refers to it. */
    static WeakReference<ClassLoader> loadAndDrop(String tag, String variant, int cycle) throws Exception {
        App b = new App("b");
        CountDownLatch ready = new CountDownLatch(4);
        List<Object> sockets = new CopyOnWriteArrayList<>();
        call(b, "load", ready, sockets, variant.equals("leak"));
        if (!ready.await(30, TimeUnit.SECONDS)) throw new IllegalStateException("not ready");
        String extra = System.getProperty("probe.extrajar", "");
        if (!extra.isEmpty()) {
            // classes defined from a dex register its dex cache, as a real app's do
            @SuppressWarnings("deprecation") DexFile dex = new DexFile(extra);
            int defined = 0;
            for (Enumeration<String> e = dex.entries(); e.hasMoreElements() && defined < 500;) {
                try {
                    Class.forName(e.nextElement(), false, b.loader);
                    defined++;
                } catch (Throwable t) {
                    // a class whose superclass is missing here
                }
            }
            dex.close();
            if (cycle == 1) out(tag, "extra-classes-defined=" + defined);
        }
        Thread.sleep(100);
        if (cycle == 1) {
            long[] heap = Native.heapForLoader(b.loader);
            collect(null);
            out(tag, "loaded app-heap-kb=" + heap[0] / 1024 + " app-objects=" + heap[1] + " walk-ms="
                    + heap[2] / 1000 + " " + metrics());
        }
        Thread[] threads = threadsOf(b.group);
        long t0 = System.nanoTime();
        for (Thread t : threads) {
            Native.inject(t, new ThreadDeath(), true);
            t.interrupt();
        }
        for (Object s : sockets) {
            if (s instanceof FileDescriptor) Os.shutdown((FileDescriptor) s, OsConstants.SHUT_RDWR);
        }
        int alive = 0;
        for (Thread t : threads) {
            t.join(3000);
            if (t.isAlive()) alive++;
        }
        for (Object s : sockets) {
            if (!(s instanceof Socket)) continue;
            Socket socket = (Socket) s;
            int fd = socket.getFileDescriptor$().getInt$();
            socket.close();
            if (cycle == 1) {
                java.lang.reflect.Field implField = Socket.class.getDeclaredField("impl");
                implField.setAccessible(true);
                Object impl = implField.get(socket);
                java.lang.reflect.Field count = Class.forName("java.net.AbstractPlainSocketImpl").getDeclaredField("fdUseCount");
                count.setAccessible(true);
                out(tag, "client fd=" + fd + " closed=" + socket.isClosed() + " still-open="
                        + new File("/proc/self/fd/" + fd).exists() + " fdUseCount=" + count.get(impl));
            }
        }
        if (b.group.activeCount() == 0) b.group.destroy();
        out(tag, "cycle=" + cycle + " threads=" + threads.length + " not-stopped=" + alive + " stop-ms="
                + (System.nanoTime() - t0) / 1_000_000 + " uncaught=" + b.group.uncaught.size());
        return new WeakReference<>(b.loader);
    }

    /** GC until {@code loader} clears, at most 5 rounds: the round it cleared, -1 if it didn't, 0 with none. */
    static int collect(WeakReference<ClassLoader> loader) {
        int cleared = loader == null ? 0 : -1;
        for (int i = 1; i <= 5; i++) {
            Runtime.getRuntime().gc();
            System.runFinalization();
            if (loader != null && loader.get() == null) {
                cleared = i;
                break;
            }
        }
        Runtime.getRuntime().gc();
        VMRuntime.getRuntime().trimHeap();
        return cleared;
    }

    static String metrics() throws Exception {
        Runtime rt = Runtime.getRuntime();
        String[] fds = new File("/proc/self/fd").list();
        return "classes=" + VMDebug.getLoadedClassCount() + " heap-used-kb=" + (rt.totalMemory() - rt.freeMemory()) / 1024
                + " rss-kb=" + status("VmRSS") + " fds=" + (fds == null ? -1 : fds.length)
                + " app-b-mapped=" + mapped("app-b.jar") + " vm-size-kb=" + status("VmSize") + " threads="
                + threadCount();
    }

    static String status(String key) throws Exception {
        try (BufferedReader r = new BufferedReader(new FileReader("/proc/self/status"))) {
            for (String line; (line = r.readLine()) != null;) {
                if (line.startsWith(key + ":")) return line.substring(key.length() + 1).trim().split("\\s+")[0];
            }
        }
        return "?";
    }

    static boolean mapped(String name) throws Exception {
        try (BufferedReader r = new BufferedReader(new FileReader("/proc/self/maps"))) {
            for (String line; (line = r.readLine()) != null;) {
                if (line.contains(name)) return true;
            }
        }
        return false;
    }

    static String initOutcome(String name, ClassLoader loader) {
        try {
            Class.forName(name, true, loader);
            return "ok";
        } catch (Throwable t) {
            return t.getClass().getName();
        }
    }

    static String[] bootClasses() throws Exception {
        List<String> names = new ArrayList<>();
        for (String jar : System.getProperty("probe.bootjars").split(":")) {
            @SuppressWarnings("deprecation") DexFile dex = new DexFile(jar);
            for (Enumeration<String> e = dex.entries(); e.hasMoreElements();) names.add(e.nextElement());
            dex.close();
        }
        return names.toArray(new String[0]);
    }

    /** Runs {@code app.App.<method>(args)} on a thread of the app's group; its threads join the group. */
    static Object call(App app, String method, Object... args) throws Exception {
        Object[] result = new Object[1];
        String[] error = new String[1];
        Thread t = new Thread(app.group, () -> {
            try {
                result[0] = Class.forName("app.App", true, app.loader).getMethod(method, Object[].class)
                        .invoke(null, (Object) args);
            } catch (Throwable e) {
                error[0] = e + (e.getCause() != null ? " caused by " + e.getCause() : "");
            }
        }, app.name + "-call");
        t.setContextClassLoader(app.loader);
        t.start();
        t.join();
        if (error[0] != null) throw new IllegalStateException(method + ": " + error[0]);
        return result[0];
    }

    static long beats(App a) throws Exception { return (Long) call(a, "beats"); }

    static Thread[] threadsOf(ThreadGroup group) {
        Thread[] threads = new Thread[group.activeCount() + 8];
        int n = group.enumerate(threads);
        Thread[] result = new Thread[n];
        System.arraycopy(threads, 0, result, 0, n);
        return result;
    }

    static Thread find(ThreadGroup group, String name) {
        Thread t = findOrNull(group, name);
        if (t == null) throw new IllegalStateException("no thread " + name);
        return t;
    }

    static Thread findOrNull(ThreadGroup group, String name) {
        for (Thread t : threadsOf(group)) {
            if (t.getName().equals(name)) return t;
        }
        return null;
    }

    /** ART's own count, from ThreadList's dump header "DALVIK THREADS (n):". */
    static int threadCount() {
        String dump = Native.dumpThreads();
        int open = dump.indexOf("DALVIK THREADS (");
        if (open < 0) return -1;
        int start = open + "DALVIK THREADS (".length();
        return Integer.parseInt(dump.substring(start, dump.indexOf(')', start)));
    }

    static void out(String tag, String line) {
        System.out.println(tag + " " + line);
    }
}
