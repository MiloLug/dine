#ifndef ARTBRIDGE_BRIDGE_H
#define ARTBRIDGE_BRIDGE_H

// artbridge's internals, shared with dev.cpp (dev builds: DINE_DEV).

#include <jni.h>
#include <os/log.h>

#include <mutex>
#include <string>
#include <vector>

namespace dine {

os_log_t Log();

// The process has one VM. Runs attach to it once it's ready; ATL needs its own class path from
// creation on, so it only starts on a process with no VM yet.
enum class VmState { kNone, kCreating, kReady, kFailed };

extern std::mutex gLock;
extern JavaVM *gVm;
extern VmState gVmState;
// the VM's stdout and stderr, relayed to os_log; -1 until RedirectOutput
extern int gOutput;

void RedirectOutput();

// Doesn't return when creation fails: ART may have attached the thread before failing, and a
// thread that exits attached aborts the process.
JNIEnv *CreateVm(const std::string &resource_dir, const std::string &data_dir, const char *log_tags,
                 const JavaVMOption *extra, int n_extra);

// a detached thread with an 8 MiB stack; false after logging the error
bool StartVmThread(void *(*body)(void *), void *arg);

#ifdef DINE_DEV
void DevVmArgs(const std::string &resource_dir, std::string &boot_class_path, std::vector<std::string> &args);
// On the ATL main thread: at its start, once the VM exists, and as it ends.
void DevAtlThreadStarted();
void DevAtlVmCreated();
void DevAtlExited();
#else
inline void DevVmArgs(const std::string &, std::string &, std::vector<std::string> &) {}
inline void DevAtlThreadStarted() {}
inline void DevAtlVmCreated() {}
inline void DevAtlExited() {}
#endif

}  // namespace dine

#endif
