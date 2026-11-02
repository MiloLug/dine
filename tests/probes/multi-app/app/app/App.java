package app;

import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.LockSupport;

/**
 * The probes' app, loaded twice (app-a.jar, app-b.jar). Every blocking loop swallows interrupts and
 * IOExceptions, so only an injected exception ends it.
 */
public class App {
    static volatile long beats;
    static volatile boolean release;
    static volatile boolean entered;
    static volatile boolean nativeIn;
    static volatile int stormIndex;
    static final Object HELD = new Object();
    static final Object LOCK = new Object();
    static final List<Object> KEEP = new ArrayList<>();
    static CountDownLatch clinitIn;
    static CountDownLatch clinitGate;

    public static Object heartbeat(Object[] a) {
        start("a-heartbeat", () -> {
            while (true) {
                beats++;
                sleepQuietly(5);
            }
        });
        return null;
    }

    public static Object beats(Object[] a) { return beats; }

    public static Object hold(Object[] a) {
        CountDownLatch holding = (CountDownLatch) a[0];
        start("a-holder", () -> {
            synchronized (HELD) {
                holding.countDown();
                while (!release) sleepQuietly(5);
            }
        });
        return HELD;
    }

    public static Object release(Object[] a) {
        release = true;
        return null;
    }

    public static Object enter(Object[] a) {
        Object monitor = a[0];
        start("a-contender", () -> {
            synchronized (monitor) {
                entered = true;
            }
        });
        return null;
    }

    public static Object entered(Object[] a) { return entered; }

    public static Object lock(Object[] a) { return LOCK; }

    public static Object nativeIn(Object[] a) { return nativeIn; }

    /** A body for probe.cc's native caller: blocks until an injected exception ends it. */
    public static void blockingCall() {
        nativeIn = true;
        while (true) {
            try {
                Thread.sleep(1_000_000);
            } catch (InterruptedException e) {
                // only an injected exception ends this
            }
        }
    }

    /** a: kind, ready latch, an extra object for the kind, a list for the sockets it opens. */
    public static Object start(Object[] a) throws Exception {
        String kind = (String) a[0];
        CountDownLatch ready = (CountDownLatch) a[1];
        Object extra = a[2];
        @SuppressWarnings("unchecked") List<Object> sockets = (List<Object>) a[3];
        worker(kind, ready, extra, sockets);
        return null;
    }

    static void worker(String kind, CountDownLatch ready, Object extra, List<Object> sockets) throws Exception {
        String name = "b-" + kind;
        switch (kind) {
            case "wait":
                start(name, () -> {
                    synchronized (LOCK) {
                        ready.countDown();
                        while (true) {
                            try {
                                LOCK.wait();
                            } catch (InterruptedException e) {
                                // keep waiting
                            }
                        }
                    }
                });
                break;
            case "park":
                start(name, () -> {
                    ready.countDown();
                    while (true) LockSupport.park();
                });
                break;
            case "sleep":
                start(name, () -> {
                    ready.countDown();
                    while (true) sleepQuietly(1_000_000);
                });
                break;
            case "read":
                Socket client = connectedPair(sockets);
                start(name, () -> {
                    byte[] buf = new byte[64];
                    try {
                        InputStream in = client.getInputStream();
                        ready.countDown();
                        while (true) {
                            try {
                                if (in.read(buf) < 0) sleepQuietly(10);
                            } catch (java.io.IOException e) {
                                sleepQuietly(10);
                            }
                        }
                    } catch (java.io.IOException e) {
                        throw new RuntimeException(e);
                    }
                });
                break;
            case "busy":
                start(name, () -> {
                    ready.countDown();
                    long x = 0;
                    while (true) x++;
                });
                break;
            case "catchall":
                start(name, () -> {
                    ready.countDown();
                    while (true) {
                        try {
                            Thread.sleep(1_000_000);
                        } catch (Throwable t) {
                            // swallows the injected exception too
                        }
                    }
                });
                break;
            case "blocked":
                start(name, () -> {
                    ready.countDown();
                    synchronized (extra) {
                        entered = true;
                    }
                });
                break;
            case "frozen":
                start(name, () -> {
                    synchronized (LOCK) {
                        ready.countDown();
                        long x = 0;
                        while (true) x++;
                    }
                });
                break;
            case "clinit":
                clinitIn = new CountDownLatch(1);
                clinitGate = new CountDownLatch(1);
                start(name, () -> new Slow());
                clinitIn.await();
                start("b-clinit-waiter", () -> new Slow());
                ready.countDown();
                break;
            case "juclock":
                java.util.concurrent.locks.Lock lock = (java.util.concurrent.locks.Lock) extra;
                start(name, () -> {
                    ready.countDown();
                    long x = 0;
                    while (true) {
                        lock.lock();
                        try {
                            x++;
                        } finally {
                            lock.unlock();
                        }
                    }
                });
                break;
            case "storm":
                start(name, () -> storm((String[]) extra, ready, sockets));
                break;
            default:
                throw new IllegalArgumentException(kind);
        }
    }

    /** The drop probe's app: ~50 MB of small objects, 200 classes, a finalizer, four blocked threads. */
    public static Object load(Object[] a) throws Exception {
        CountDownLatch ready = (CountDownLatch) a[0];
        @SuppressWarnings("unchecked") List<Object> sockets = (List<Object>) a[1];
        boolean leak = (Boolean) a[2];
        for (int i = 0; i < 400_000; i++) KEEP.add(new byte[100]);
        for (int i = 0; i < 200; i++) KEEP.add(Class.forName("app.G" + i).newInstance());
        new Fin();
        KEEP.add(new Fin());
        if (leak) Thread.setDefaultUncaughtExceptionHandler(new LeakHandler());
        for (String kind : new String[] {"wait", "park", "sleep", "read"}) worker(kind, ready, null, sockets);
        return null;
    }

    /**
     * Initializes every class in {@code classes} from {@link #stormIndex} on; names whose initializer
     * the probe's Marker ended go to {@code hits}. The driver restarts it when a Marker escapes.
     */
    static void storm(String[] classes, CountDownLatch ready, List<Object> hits) {
        ready.countDown();
        while (stormIndex < classes.length) {
            try {
                for (; stormIndex < classes.length; stormIndex++) {
                    try {
                        Class.forName(classes[stormIndex], true, null);
                    } catch (ExceptionInInitializerError e) {
                        if (e.getCause() != null && e.getCause().getClass().getName().equals("probe.Marker")) {
                            hits.add(classes[stormIndex]);
                        }
                    } catch (LinkageError e) {
                        // fails to initialize without the probe too
                    }
                }
            } catch (Throwable t) {
                stormIndex++;
            }
        }
    }

    public static Object stormIndex(Object[] a) { return stormIndex; }

    static Socket connectedPair(List<Object> sockets) throws Exception {
        ServerSocket server = new ServerSocket(0, 1, InetAddress.getLoopbackAddress());
        Socket client = new Socket(InetAddress.getLoopbackAddress(), server.getLocalPort());
        Socket peer = server.accept();
        KEEP.add(server);
        KEEP.add(peer);
        sockets.add(client);
        sockets.add(client.getFileDescriptor$());
        System.out.println("app sockets server=" + server.getFileDescriptor$().getInt$() + " client="
                + client.getFileDescriptor$().getInt$() + " peer=" + peer.getFileDescriptor$().getInt$());
        return client;
    }

    static void start(String name, Runnable body) {
        Thread t = new Thread(body, name);
        t.setDaemon(true);
        t.start();
    }

    static void sleepQuietly(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            // only an injected exception ends a loop
        }
    }

    static class Fin {
        @Override protected void finalize() { beats++; }
    }

    static class LeakHandler implements Thread.UncaughtExceptionHandler {
        @Override public void uncaughtException(Thread t, Throwable e) {}
    }
}
