#include "dineart.h"

#include <atl/atl_embedded.h>
#include <dlfcn.h>
#include <errno.h>
#include <jni.h>
#include <mach/mach.h>
#include <os/log.h>
#include <pthread.h>
#include <pwd.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include <map>
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
  for (const char *name : {"JNI_CreateJavaVM", "JNI_OnLoad_javacore", "JNI_OnLoad_openjdk",
                           "JNI_OnLoad_dinejniargs"}) {
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
  bool create_vm;
};

// The process has one VM. Runs attach to it once it's ready; ATL needs its own class path from
// creation on, so it only starts on a process with no VM yet.
enum class VmState { kNone, kCreating, kReady, kFailed };

std::mutex gLock;
JavaVM *gVm = nullptr;
VmState gVmState = VmState::kNone;
bool gRunning = false;

// Doesn't return when creation fails: ART may have attached the thread before failing, and a
// thread that exits attached aborts the process.
JNIEnv *CreateVm(const std::string &resource_dir, const std::string &data_dir, const char *log_tags,
                 const JavaVMOption *extra, int n_extra) {
  setenv("ANDROID_ROOT", resource_dir.c_str(), 1);
  setenv("ANDROID_DATA", data_dir.c_str(), 1);
  setenv("XDG_CACHE_HOME", data_dir.c_str(), 1);
  setenv("ANDROID_LOG_TAGS", log_tags, 1);
  setenv("ANDROID_PRINTF_LOG", "brief", 1);

  std::string boot = "-Xbootclasspath:";
  for (const char *jar : kBootJars) {
    if (jar != kBootJars[0]) boot += ':';
    boot += resource_dir + "/" + jar + "-hostdex.jar";
  }
  std::vector<std::string> args = {
      boot, "-Xint", "-Xusejit:false", "-Xnorelocate", "-XX:DumpNativeStackOnSigQuit:false",
      "-Xcheck:jni", "-Djava.io.tmpdir=" + data_dir,
  };
  std::vector<JavaVMOption> options;
  for (const std::string &arg : args) options.push_back({const_cast<char *>(arg.c_str()), nullptr});
  options.insert(options.end(), extra, extra + n_extra);
  JavaVMInitArgs init = {JNI_VERSION_1_6, static_cast<jint>(options.size()), options.data(), JNI_FALSE};

  JavaVM *vm = nullptr;
  JNIEnv *env = nullptr;
  if (JNI_CreateJavaVM(&vm, &env, &init) != JNI_OK) {
    {
      // ART keeps the failed runtime: no second try in this process
      std::lock_guard<std::mutex> lock(gLock);
      gVmState = VmState::kFailed;
    }
    os_log_error(Log(), "art JNI_CreateJavaVM failed");
    for (;;) pause();
  }
  std::lock_guard<std::mutex> lock(gLock);
  gVm = vm;
  gVmState = VmState::kReady;
  os_log(Log(), "art vm created");
  return env;
}

// One loader per jar for the VM's lifetime: ART won't open a native library again from a second
// loader, so a rerun must reuse the loader that loaded it.
std::map<std::string, jobject> gLoaders;

jobject LoaderFor(JNIEnv *env, const std::string &class_path) {
  auto it = gLoaders.find(class_path);
  if (it != gLoaders.end()) return it->second;
  jclass loader_class = env->FindClass("java/lang/ClassLoader");
  jobject system = env->CallStaticObjectMethod(
      loader_class, env->GetStaticMethodID(loader_class, "getSystemClassLoader", "()Ljava/lang/ClassLoader;"));
  jclass path_class = env->FindClass("dalvik/system/PathClassLoader");
  jmethodID init = env->GetMethodID(path_class, "<init>", "(Ljava/lang/String;Ljava/lang/ClassLoader;)V");
  jobject loader = env->NewObject(path_class, init, env->NewStringUTF(class_path.c_str()), system);
  if (env->ExceptionCheck()) return nullptr;
  return gLoaders[class_path] = env->NewGlobalRef(loader);
}

void RunMain(JNIEnv *env, const std::string &class_path, const std::string &main_class) {
  jobject loader = LoaderFor(env, class_path);
  jclass cls = nullptr;
  if (loader) {
    jmethodID load = env->GetMethodID(env->FindClass("java/lang/ClassLoader"), "loadClass",
                                      "(Ljava/lang/String;)Ljava/lang/Class;");
    cls = static_cast<jclass>(env->CallObjectMethod(loader, load, env->NewStringUTF(main_class.c_str())));
  }
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
  if (run->create_vm) {
    env = CreateVm(run->resource_dir, run->data_dir, "*:w", nullptr, 0);
  } else {
    gVm->AttachCurrentThread(&env, nullptr);
  }
  if (env) {
    RunMain(env, run->class_path, run->main_class);
    gVm->DetachCurrentThread();
  }
  std::lock_guard<std::mutex> lock(gLock);
  gRunning = false;
  return nullptr;
}

constexpr size_t kVmThreadStack = 8 << 20;

// a detached thread with kVmThreadStack; false after logging the error
bool StartVmThread(void *(*body)(void *), void *arg) {
  pthread_attr_t attr;
  pthread_attr_init(&attr);
  pthread_attr_setstacksize(&attr, kVmThreadStack);
  pthread_t thread;
  int rc = pthread_create(&thread, &attr, body, arg);
  pthread_attr_destroy(&attr);
  if (rc != 0) {
    os_log_error(Log(), "art pthread_create: %{public}s", strerror(rc));
    return false;
  }
  pthread_detach(thread);
  return true;
}

struct AtlRun {
  std::string resource_dir, atl_dir, data_dir, apk, activity;
  atl_embedded_listener listener;
};

bool gAtlStarted = false;
bool gAtlExited = false;
// the ATL main thread's stack, for AtlProbe
char *gAtlStackLow = nullptr;
char *gAtlStackTop = nullptr;

// The stack's pages fault in on first use and nothing touches them ahead (ART's stack-overflow
// checks are explicit), so the lowest resident page marks the deepest use so far.
size_t AtlStackUsed() {
  // mincore writes a byte for every page the range touches; the stack bounds needn't be aligned
  uintptr_t page = getpagesize();
  uintptr_t low = reinterpret_cast<uintptr_t>(gAtlStackLow) & ~(page - 1);
  uintptr_t top = (reinterpret_cast<uintptr_t>(gAtlStackTop) + page - 1) & ~(page - 1);
  std::vector<char> pages((top - low) / page);
  if (mincore(reinterpret_cast<void *>(low), top - low, pages.data()) != 0) {
    os_log_error(Log(), "atl probe: mincore: %{public}s", strerror(errno));
    return 0;
  }
  size_t i = 0;
  // MINCORE_ANONYMOUS alone also marks pages never touched; PAGED_OUT is compressed
  while (i < pages.size() && !(pages[i] & (MINCORE_INCORE | MINCORE_PAGED_OUT))) i++;
  return (pages.size() - i) * page;
}

void AtlProbe(const char *phase) {
  task_vm_info_data_t info;
  mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
  kern_return_t kr = task_info(mach_task_self(), TASK_VM_INFO, reinterpret_cast<task_info_t>(&info), &count);
  if (kr != KERN_SUCCESS) return os_log_error(Log(), "atl probe %{public}s: task_info %d", phase, kr);
  os_log(Log(), "atl probe %{public}s: stack used %zu KiB of %zu KiB, phys_footprint %llu MiB, peak %lld MiB",
         phase, AtlStackUsed() >> 10, static_cast<size_t>(gAtlStackTop - gAtlStackLow) >> 10,
         info.phys_footprint >> 20, info.ledger_phys_footprint_peak >> 20);
}

void AtlExited() {
  std::lock_guard<std::mutex> lock(gLock);
  gAtlExited = true;
}

void *AtlThread(void *arg) {
  std::unique_ptr<AtlRun> run(static_cast<AtlRun *>(arg));
  {
    std::lock_guard<std::mutex> lock(gLock);
    gAtlStackTop = static_cast<char *>(pthread_get_stackaddr_np(pthread_self()));
    gAtlStackLow = gAtlStackTop - pthread_get_stacksize_np(pthread_self());
  }
  os_log(Log(), "atl start");
  AtlProbe("before vm");

  std::string app_data = run->data_dir + "/atl";
  mkdir(app_data.c_str(), 0755);
  // C and ATL's Java (ATLPaths) both read the app data dir from here
  setenv("ANDROID_APP_DATA_DIR", app_data.c_str(), 1);
  setenv("ATL_DUMP_VIEWTREE", "1", 1);

  std::string api_impl = run->atl_dir + "/api-impl.jar";
  std::string framework_res = run->atl_dir + "/framework-res.apk";
  atl_embedded_config config = {
      .api_impl_jar = api_impl.c_str(),
      .framework_res_apk = framework_res.c_str(),
      .apk = run->apk.c_str(),
      .activity = run->activity.empty() ? nullptr : run->activity.c_str(),
      .listener = &run->listener,
  };
  int n_options;
  JavaVMOption *options = atl_embedded_vm_options(&config, &n_options);
  if (!options) {
    os_log_error(Log(), "atl options failed");
    {
      std::lock_guard<std::mutex> lock(gLock);
      gVmState = VmState::kNone;
    }
    AtlExited();
    if (run->listener.exited) run->listener.exited(run->listener.context, -1);
    return nullptr;
  }
  // *:i: ATL logs its lifecycle (onResume) at info
  JNIEnv *env = CreateVm(run->resource_dir, run->data_dir, "*:i", options, n_options);
  atl_embedded_vm_options_free(options, n_options);
  AtlProbe("vm created");

  int rc = atl_embedded_main(env, &config);
  os_log(Log(), "atl main returned %d", rc);
  // ART aborts the process when a thread it knows exits attached
  gVm->DetachCurrentThread();
  AtlExited();
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
  if (gVmState == VmState::kFailed) {
    os_log_error(Log(), "art: VM creation failed earlier in this process: relaunch Dine");
    return -1;
  }
  if (gRunning || gVmState == VmState::kCreating) {
    os_log_error(Log(), "art: a run is still active");
    return -1;
  }
  if (gOutput < 0) RedirectOutput();
  bool create = gVmState == VmState::kNone;
  auto *run = new Run{resource_dir, data_dir, class_path, main_class, create};
  if (!StartVmThread(VmThread, run)) {
    delete run;
    return -1;
  }
  if (create) gVmState = VmState::kCreating;
  gRunning = true;
  return 0;
}

int dine_atl_run(const char *resource_dir, const char *atl_dir, const char *data_dir,
                 const char *apk, const char *activity, const atl_embedded_listener *listener) {
  std::lock_guard<std::mutex> lock(gLock);
  if (gAtlStarted) {
    os_log_error(Log(), "atl already ran in this process: relaunch Dine");
    return -1;
  }
  if (gVmState != VmState::kNone) {
    os_log_error(Log(), "atl needs a process without a VM: relaunch Dine");
    return -1;
  }
  if (gOutput < 0) RedirectOutput();
  auto *run = new AtlRun{resource_dir, atl_dir, data_dir, apk, activity ? activity : "",
                         listener ? *listener : atl_embedded_listener{}};
  if (!StartVmThread(AtlThread, run)) {
    delete run;
    return -1;
  }
  gAtlStarted = true;
  gVmState = VmState::kCreating;
  return 0;
}

void dine_atl_probe(void) {
  std::lock_guard<std::mutex> lock(gLock);
  if (!gAtlStackLow) return os_log_error(Log(), "atl probe: atl not started");
  // its stack is gone
  if (gAtlExited) return os_log_error(Log(), "atl probe: the atl thread has exited");
  AtlProbe("now");
}
