package app;

class Slow {
    static {
        App.clinitIn.countDown();
        while (true) {
            try {
                App.clinitGate.await();
                break;
            } catch (InterruptedException e) {
                // only an injected exception ends this
            }
        }
    }
}
