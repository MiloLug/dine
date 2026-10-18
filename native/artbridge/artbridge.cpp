#include "dineart.h"

#include <dlfcn.h>
#include <errno.h>
#include <jni.h>
#include <os/log.h>
#include <pthread.h>
#include <pwd.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace {

os_log_t Log() {
  static os_log_t log = os_log_create("dev.dine.Dine", "art");
  return log;
}

std::string Hex(const void *p) {
  char buf[32];
  snprintf(buf, sizeof buf, "%p", p);
  return buf;
}

std::string ErrnoText(int err) { return std::string("errno ") + std::to_string(err) + " " + strerror(err); }

std::string gProbe;

void Report(const char *name, const std::string &value) {
  os_log(Log(), "art probe %{public}s %{public}s", name, value.c_str());
  gProbe += name;
  gProbe += ' ';
  gProbe += value;
  gProbe += '\n';
}

void ProbeReservation() {
  constexpr size_t kUnit = 64ull << 20;
  auto reserve = [](size_t size) {
    void *p = mmap(nullptr, size, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
    return p == MAP_FAILED ? nullptr : p;
  };
  // Largest n in [0, 1024] with an n * 64 MB reservation, assuming smaller ones always fit.
  size_t good = 0, bad = 1025;
  while (bad - good > 1) {
    size_t mid = (good + bad) / 2;
    if (void *p = reserve(mid * kUnit)) {
      munmap(p, mid * kUnit);
      good = mid;
    } else {
      bad = mid;
    }
  }
  void *at = good ? reserve(good * kUnit) : nullptr;
  if (at) munmap(at, good * kUnit);
  Report("reserve-max", std::to_string(good * 64) + " MB at " + Hex(at));
}

void ProbeLowHint() {
  void *hint = reinterpret_cast<void *>(0x10000000);
  void *p = mmap(hint, 16384, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
  if (p == MAP_FAILED) return Report("low-hint", ErrnoText(errno));
  munmap(p, 16384);
  Report("low-hint", Hex(hint) + " got " + Hex(p));
}

void ProbeFork() {
  pid_t pid = fork();
  if (pid == 0) _exit(0);
  if (pid < 0) return Report("fork", ErrnoText(errno));
  waitpid(pid, nullptr, 0);
  Report("fork", "child " + std::to_string(pid));
}

void ProbeStack(size_t size) {
  void *stack = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
  pthread_attr_t attr;
  pthread_attr_init(&attr);
  int rc = pthread_attr_setstack(&attr, stack, size);
  pthread_attr_destroy(&attr);
  munmap(stack, size);
  Report(("setstack-" + std::to_string(size / 1024) + "k").c_str(), rc ? ErrnoText(rc) : "ok");
}

void ProbeMprotect() {
  constexpr size_t kSize = 64 * 1024;
  void *p = mmap(nullptr, kSize, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
  int rc = mprotect(static_cast<char *>(p) + 4096, 4096, PROT_NONE);
  Report("mprotect-4k-offset", rc ? ErrnoText(errno) : "ok");
  munmap(p, kSize);
}

void ProbeSymbols() {
  void *self = dlopen(nullptr, RTLD_NOW);
  for (const char *name : {"JNI_CreateJavaVM", "JNI_OnLoad_javacore", "JNI_OnLoad_openjdk"}) {
    Report((std::string("dlsym-") + name).c_str(), self && dlsym(self, name) ? "found" : "missing");
  }
}

void ProbePasswd() {
  struct passwd pw, *found = nullptr;
  char buf[4096];
  int rc = getpwuid_r(getuid(), &pw, buf, sizeof buf, &found);
  if (rc || !found) return Report("getpwuid_r", rc ? ErrnoText(rc) : "no entry");
  Report("getpwuid_r", std::string("uid ") + std::to_string(getuid()) + " name " + pw.pw_name +
                           " home " + pw.pw_dir);
}

// The VM's fds 1 and 2 write into a socket; Relay sends each line to os_log. A socket rather
// than a pipe so Drain can read without blocking while Relay blocks on the same descriptor.
int gOutput = -1;

void EmitLines(std::string &pending, const char *data, size_t size) {
  pending.append(data, size);
  for (size_t nl; (nl = pending.find('\n')) != std::string::npos; pending.erase(0, nl + 1)) {
    os_log(Log(), "%{public}s", pending.substr(0, nl).c_str());
  }
}

void *Relay(void *) {
  std::string pending;
  char buf[4096];
  for (;;) {
    ssize_t n = recv(gOutput, buf, sizeof buf, 0);
    if (n < 0 && errno == EINTR) continue;
    if (n <= 0) return nullptr;
    EmitLines(pending, buf, n);
  }
}

// The process is about to die: whatever Relay hasn't read yet would be lost.
void Drain() {
  std::string pending;
  char buf[4096];
  for (ssize_t n; (n = recv(gOutput, buf, sizeof buf, MSG_DONTWAIT)) > 0;) EmitLines(pending, buf, n);
  if (!pending.empty()) os_log(Log(), "%{public}s", pending.c_str());
}

void OnAbort(int sig) {
  Drain();
  signal(sig, SIG_DFL);
  raise(sig);
}

void RedirectOutput() {
  int fds[2];
  if (socketpair(AF_UNIX, SOCK_STREAM, 0, fds) != 0) {
    os_log_error(Log(), "art socketpair: %{public}s", strerror(errno));
    return;
  }
  dup2(fds[1], STDOUT_FILENO);
  dup2(fds[1], STDERR_FILENO);
  close(fds[1]);
  gOutput = fds[0];
  setvbuf(stdout, nullptr, _IOLBF, 0);
  pthread_t thread;
  pthread_create(&thread, nullptr, Relay, nullptr);
  pthread_detach(thread);
  // LOG(FATAL) ends in abort(); System.exit in exit().
  struct sigaction sa = {};
  sa.sa_handler = OnAbort;
  sigaction(SIGABRT, &sa, nullptr);
  atexit(Drain);
}

// ART's default order (dine-art/art/runtime/parsed_options.cc), which a static link can't derive:
// it looks next to libart.so.
constexpr const char *kBootJars[] = {
    "core-oj", "apachehttp", "apache-xml", "bouncycastle", "core-junit",
    "core-libart", "hamcrest", "junit-runner", "okhttp", "wolfssljni",
};

struct Run {
  std::string resource_dir, data_dir, class_path, main_class;
};

std::mutex gLock;
JavaVM *gVm = nullptr;
bool gRunning = false;

JNIEnv *CreateVm(const Run &run) {
  setenv("ANDROID_ROOT", run.resource_dir.c_str(), 1);
  setenv("ANDROID_DATA", run.data_dir.c_str(), 1);
  setenv("XDG_CACHE_HOME", run.data_dir.c_str(), 1);
  setenv("ANDROID_LOG_TAGS", "*:w", 1);
  setenv("ANDROID_PRINTF_LOG", "brief", 1);

  std::string boot = "-Xbootclasspath:";
  for (const char *jar : kBootJars) {
    if (jar != kBootJars[0]) boot += ':';
    boot += run.resource_dir + "/" + jar + "-hostdex.jar";
  }
  std::vector<std::string> args = {
      boot, "-Xint", "-Xusejit:false", "-Xnorelocate", "-XX:DumpNativeStackOnSigQuit:false",
      "-Xcheck:jni", "-Djava.io.tmpdir=" + run.data_dir, "-cp", run.class_path,
  };
  std::vector<JavaVMOption> options;
  for (const std::string &arg : args) options.push_back({const_cast<char *>(arg.c_str()), nullptr});
  JavaVMInitArgs init = {JNI_VERSION_1_6, static_cast<jint>(options.size()), options.data(), JNI_FALSE};

  JNIEnv *env = nullptr;
  if (JNI_CreateJavaVM(&gVm, &env, &init) != JNI_OK) {
    os_log_error(Log(), "art JNI_CreateJavaVM failed");
    gVm = nullptr;
    return nullptr;
  }
  os_log(Log(), "art vm created");
  return env;
}

void RunMain(JNIEnv *env, const std::string &main_class) {
  jclass cls = env->FindClass(main_class.c_str());
  jmethodID main = cls ? env->GetStaticMethodID(cls, "main", "([Ljava/lang/String;)V") : nullptr;
  if (main) {
    jobjectArray argv = env->NewObjectArray(0, env->FindClass("java/lang/String"), nullptr);
    env->CallStaticVoidMethod(cls, main, argv);
  }
  if (env->ExceptionCheck()) {
    env->ExceptionDescribe();
    os_log_error(Log(), "art main threw");
  } else {
    os_log(Log(), "art main returned");
  }
}

void *VmThread(void *arg) {
  std::unique_ptr<Run> run(static_cast<Run *>(arg));
  JNIEnv *env = nullptr;
  if (gVm) {
    gVm->AttachCurrentThread(&env, nullptr);
  } else {
    env = CreateVm(*run);
  }
  if (env) {
    RunMain(env, run->main_class);
    gVm->DetachCurrentThread();
  }
  std::lock_guard<std::mutex> lock(gLock);
  gRunning = false;
  return nullptr;
}

}  // namespace

const char *dine_art_probe(void) {
  gProbe.clear();
  Report("page-size", std::to_string(getpagesize()) + " sysconf " + std::to_string(sysconf(_SC_PAGESIZE)));
  ProbeReservation();
  ProbeLowHint();
  ProbeFork();
  ProbeStack(68 * 1024);
  ProbeStack(80 * 1024);
  ProbeMprotect();
  ProbeSymbols();
  ProbePasswd();
  os_log(Log(), "art probe done");
  return gProbe.c_str();
}

int dine_art_run(const char *resource_dir, const char *data_dir, const char *class_path,
                 const char *main_class) {
  std::lock_guard<std::mutex> lock(gLock);
  if (gRunning) return -1;
  if (gOutput < 0) RedirectOutput();
  pthread_attr_t attr;
  pthread_attr_init(&attr);
  pthread_attr_setstacksize(&attr, 8 << 20);
  pthread_t thread;
  auto *run = new Run{resource_dir, data_dir, class_path, main_class};
  int rc = pthread_create(&thread, &attr, VmThread, run);
  pthread_attr_destroy(&attr);
  if (rc != 0) {
    delete run;
    os_log_error(Log(), "art pthread_create: %{public}s", strerror(rc));
    return -1;
  }
  pthread_detach(thread);
  gRunning = true;
  return 0;
}
