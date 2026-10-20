#include "bridge.h"
#include "dineart.h"

#include <atl/atl_embedded.h>
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#include <memory>
#include <string>
#include <vector>

namespace dine {

os_log_t Log() {
  static os_log_t log = os_log_create("dev.dine.Dine", "art");
  return log;
}

std::mutex gLock;
JavaVM *gVm = nullptr;
VmState gVmState = VmState::kNone;
// fds 1 and 2 write into a socket; Relay sends each line to os_log. A socket rather than a pipe so
// Drain can read without blocking while Relay blocks on the same descriptor.
int gOutput = -1;

namespace {

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

}  // namespace

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

namespace {

// ART's default order (dine-art/art/runtime/parsed_options.cc), which a static link can't derive:
// it looks next to libart.so.
constexpr const char *kBootJars[] = {
    "core-oj", "apachehttp", "apache-xml", "bouncycastle", "core-junit",
    "core-libart", "hamcrest", "junit-runner", "okhttp", "wolfssljni",
};

constexpr size_t kVmThreadStack = 8 << 20;

}  // namespace

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

namespace {

struct AtlRun {
  std::string resource_dir, atl_dir, data_dir, apk, activity;
  atl_embedded_listener listener;
};

bool gAtlStarted = false;

void *AtlThread(void *arg) {
  std::unique_ptr<AtlRun> run(static_cast<AtlRun *>(arg));
  os_log(Log(), "atl start");
  DevAtlThreadStarted();

  std::string app_data = run->data_dir + "/atl";
  mkdir(app_data.c_str(), 0755);
  // C and ATL's Java (ATLPaths) both read the app data dir from here
  setenv("ANDROID_APP_DATA_DIR", app_data.c_str(), 1);

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
    DevAtlExited();
    if (run->listener.exited) run->listener.exited(run->listener.context, -1);
    return nullptr;
  }
  // *:i: ATL logs its lifecycle (onResume) at info
  JNIEnv *env = CreateVm(run->resource_dir, run->data_dir, "*:i", options, n_options);
  atl_embedded_vm_options_free(options, n_options);
  DevAtlVmCreated();

  int rc = atl_embedded_main(env, &config);
  os_log(Log(), "atl main returned %d", rc);
  // ART aborts the process when a thread it knows exits attached
  gVm->DetachCurrentThread();
  DevAtlExited();
  return nullptr;
}

}  // namespace
}  // namespace dine

int dine_atl_run(const char *resource_dir, const char *atl_dir, const char *data_dir,
                 const char *apk, const char *activity, const atl_embedded_listener *listener) {
  using namespace dine;
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
