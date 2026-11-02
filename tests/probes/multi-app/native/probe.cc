// JNI side of the multi-app probes: libart internals the Java driver can't reach. build.sh
// compiles it with libart's own flags, so the inline header code matches libart's layouts.
#include <dlfcn.h>
#include <jni.h>
#include <pthread.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <chrono>
#include <cstdio>
#include <sstream>
#include <string>

#include "asm_defines.h"
#include "base/mutex.h"
#include "gc/heap-visit-objects-inl.h"
#include "gc/heap.h"
#include "handle_scope-inl.h"
#include "jni/jni_env_ext.h"
#include "mirror/class-inl.h"
#include "mirror/object-inl.h"
#include "mirror/object_reference.h"
#include "mirror/throwable.h"
#include "monitor.h"
#include "obj_ptr-inl.h"
#include "runtime.h"
#include "scoped_thread_state_change-inl.h"
#include "thread-current-inl.h"
#include "thread.h"
#include "thread_list.h"

namespace {

constexpr auto kPs = art::kRuntimePointerSize;
// asm_defines.h comes from libart's own compile: a flag that differs here moves these offsets.
static_assert(art::Thread::ExceptionOffset<kPs>().Int32Value() == THREAD_EXCEPTION_OFFSET);
static_assert(art::Thread::SelfOffset<kPs>().Int32Value() == THREAD_SELF_OFFSET);
static_assert(art::Thread::TopOfManagedStackOffset<kPs>().Int32Value() == THREAD_TOP_QUICK_FRAME_OFFSET);
static_assert(art::Thread::ThreadLocalAllocStackEndOffset<kPs>().Int32Value() ==
              THREAD_LOCAL_ALLOC_STACK_END_OFFSET);
static_assert(art::Thread::InterpreterCacheOffset<kPs>().Int32Value() == THREAD_INTERPRETER_CACHE_OFFSET);
static_assert(art::mirror::Class::StatusOffset().Int32Value() == MIRROR_CLASS_STATUS_OFFSET);
static_assert(art::mirror::Object::MonitorOffset().Int32Value() == MIRROR_OBJECT_LOCK_WORD_OFFSET);

JavaVM *gVm;

// gHeapReferenceBase is an inline variable: this library has its own copy, and libart's code reads
// libart's copy without a relocation, so the loader never unifies them. LIBART_HEAP_REFERENCE_BASE
// is libart's copy's address relative to libart's load base (build.sh).
uintptr_t *LibartHeapReferenceBase() {
  void *art = dlopen("libart.so", RTLD_NOW | RTLD_NOLOAD);
  void *symbol = art == nullptr ? nullptr : dlsym(art, "JNI_GetCreatedJavaVMs");
  Dl_info info;
  if (symbol == nullptr || dladdr(symbol, &info) == 0) return nullptr;
  return reinterpret_cast<uintptr_t *>(static_cast<char *>(info.dli_fbase) + LIBART_HEAP_REFERENCE_BASE);
}

jstring Check(JNIEnv *env, jclass, jobject peer) {
  std::string err;
  uintptr_t *libart_base = LibartHeapReferenceBase();
  if (libart_base == nullptr || *libart_base == 0) err += "no gHeapReferenceBase in libart; ";
  else if (*libart_base != art::mirror::gHeapReferenceBase) err += "gHeapReferenceBase differs from libart's; ";
  art::Thread *self = art::Thread::Current();
  if (self == nullptr) return env->NewStringUTF("Thread::Current is null");
  if (reinterpret_cast<JNIEnv *>(self->GetJniEnv()) != env) err += "GetJniEnv != env; ";
  if (self->GetTid() != static_cast<pid_t>(syscall(SYS_gettid))) err += "GetTid != gettid; ";
  {
    art::ScopedObjectAccess soa(env);
    art::MutexLock mu(soa.Self(), *art::Locks::thread_list_lock_);
    if (art::Thread::FromManagedThread(soa, peer) != self) err += "FromManagedThread(current) != Current; ";
    std::string descriptor;
    descriptor = soa.Decode<art::mirror::Object>(peer)->GetClass()->GetDescriptor(&descriptor);
    if (descriptor != "Ljava/lang/Thread;") err += "peer's class is " + descriptor + "; ";
  }
  return env->NewStringUTF(err.empty() ? "ok" : err.c_str());
}

// JVMTI StopThread's closure (ti_thread.cc) without its deoptimization, which -Xint makes moot.
// Notify wakes only Object.wait; unpark also ends a LockSupport.park.
struct StopClosure : public art::Closure {
  StopClosure(art::Handle<art::mirror::Throwable> exception, bool unpark) : exception_(exception), unpark_(unpark) {}
  void Run(art::Thread *me) override REQUIRES_SHARED(art::Locks::mutator_lock_) {
    me->SetAsyncException(exception_.Get());
    me->Notify();
    if (unpark_) me->Unpark();
  }
  art::Handle<art::mirror::Throwable> exception_;
  bool unpark_;
};

jint Inject(JNIEnv *env, jclass, jobject peer, jthrowable exception, jboolean unpark) {
  art::ScopedObjectAccess soa(env);
  art::Thread *self = soa.Self();
  art::StackHandleScope<1> hs(self);
  art::Handle<art::mirror::Throwable> exc(hs.NewHandle(soa.Decode<art::mirror::Throwable>(exception)));
  art::Locks::thread_list_lock_->ExclusiveLock(self);
  art::Thread *target = art::Thread::FromManagedThread(soa, peer);
  if (target == nullptr || target->GetState() == art::ThreadState::kTerminated) {
    art::Locks::thread_list_lock_->ExclusiveUnlock(self);
    return 2;
  }
  if (target->GetState() == art::ThreadState::kStarting || target->IsStillStarting()) {
    art::Locks::thread_list_lock_->ExclusiveUnlock(self);
    return 1;
  }
  StopClosure closure(exc, unpark == JNI_TRUE);
  // releases thread_list_lock_
  return target->RequestSynchronousCheckpoint(&closure) ? 0 : 3;
}

// Called in kNative: SuspendThreadByPeer must not hold the mutator lock.
jlong Suspend(JNIEnv *, jclass, jobject peer) {
  bool timed_out = false;
  art::Thread *t = art::Runtime::Current()->GetThreadList()->SuspendThreadByPeer(
      peer, true, art::SuspendReason::kInternal, &timed_out);
  return timed_out ? -1 : reinterpret_cast<jlong>(t);
}

jboolean Resume(JNIEnv *, jclass, jlong thread) {
  return art::Runtime::Current()->GetThreadList()->Resume(reinterpret_cast<art::Thread *>(thread),
                                                          art::SuspendReason::kInternal);
}

jstring DumpThreads(JNIEnv *env, jclass) {
  std::ostringstream os;
  art::Runtime::Current()->GetThreadList()->Dump(os, false);
  return env->NewStringUTF(os.str().c_str());
}

jint LockOwner(JNIEnv *env, jclass, jobject obj) {
  art::ScopedObjectAccess soa(env);
  return static_cast<jint>(art::Monitor::GetLockOwnerThreadId(soa.Decode<art::mirror::Object>(obj)));
}

// Bytes and objects whose class the loader defined, and the walk's time: {bytes, objects, micros}.
jlongArray HeapForLoader(JNIEnv *env, jclass, jobject loader) {
  jlong out[3] = {0, 0, 0};
  {
    art::ScopedObjectAccess soa(env);
    art::ObjPtr<art::mirror::Object> target = soa.Decode<art::mirror::Object>(loader);
    auto start = std::chrono::steady_clock::now();
    art::Runtime::Current()->GetHeap()->VisitObjects([&](art::mirror::Object *obj)
                                                         REQUIRES_SHARED(art::Locks::mutator_lock_) {
      if (obj->GetClass()->GetClassLoader() == target) {
        out[0] += obj->SizeOf();
        out[1]++;
      }
    });
    out[2] = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - start)
                 .count();
  }
  jlongArray result = env->NewLongArray(3);
  env->SetLongArrayRegion(result, 0, 3, out);
  return result;
}

struct Caller {
  jobject group;
  jclass cls;
  jmethodID method;
  bool careless;
};

std::string ClassName(JNIEnv *env, jobject obj) {
  jclass cls = env->GetObjectClass(obj);
  jclass class_class = env->FindClass("java/lang/Class");
  jmethodID get_name = env->GetMethodID(class_class, "getName", "()Ljava/lang/String;");
  auto name = static_cast<jstring>(env->CallObjectMethod(cls, get_name));
  const char *chars = env->GetStringUTFChars(name, nullptr);
  std::string result(chars);
  env->ReleaseStringUTFChars(name, chars);
  return result;
}

// An artbridge-like host thread: C attached through JNI, calling into the app in a loop.
void *CallerMain(void *arg) {
  auto *c = static_cast<Caller *>(arg);
  JNIEnv *env = nullptr;
  JavaVMAttachArgs args{JNI_VERSION_1_6, const_cast<char *>("b-native"), c->group};
  if (gVm->AttachCurrentThread(&env, &args) != JNI_OK) {
    fprintf(stderr, "native: attach failed\n");
    return nullptr;
  }
  for (int call = 0;; call++) {
    env->CallStaticVoidMethod(c->cls, c->method);
    if (!env->ExceptionCheck()) continue;
    if (c->careless) {
      fprintf(stderr, "native: call %d returned with an exception pending; calling again\n", call);
      fflush(stderr);
      env->CallStaticVoidMethod(c->cls, c->method);
      fprintf(stderr, "native: the second call returned\n");
    }
    jthrowable e = env->ExceptionOccurred();
    env->ExceptionClear();
    fprintf(stderr, "native: call %d returned with %s pending; detaching\n", call, ClassName(env, e).c_str());
    fflush(stderr);
    env->DeleteLocalRef(e);
    break;
  }
  env->DeleteGlobalRef(c->group);
  env->DeleteGlobalRef(c->cls);
  delete c;
  // a thread that exits while attached is a FATAL
  gVm->DetachCurrentThread();
  return nullptr;
}

void StartNativeCaller(JNIEnv *env, jclass, jobject group, jclass cls, jstring method, jboolean careless) {
  const char *name = env->GetStringUTFChars(method, nullptr);
  auto *c = new Caller{env->NewGlobalRef(group), static_cast<jclass>(env->NewGlobalRef(cls)),
                       env->GetStaticMethodID(cls, name, "()V"), careless == JNI_TRUE};
  env->ReleaseStringUTFChars(method, name);
  pthread_t thread;
  pthread_create(&thread, nullptr, CallerMain, c);
  pthread_detach(thread);
}

const JNINativeMethod kMethods[] = {
    {"check", "(Ljava/lang/Thread;)Ljava/lang/String;", reinterpret_cast<void *>(Check)},
    {"inject", "(Ljava/lang/Thread;Ljava/lang/Throwable;Z)I", reinterpret_cast<void *>(Inject)},
    {"suspend", "(Ljava/lang/Thread;)J", reinterpret_cast<void *>(Suspend)},
    {"resume", "(J)Z", reinterpret_cast<void *>(Resume)},
    {"dumpThreads", "()Ljava/lang/String;", reinterpret_cast<void *>(DumpThreads)},
    {"lockOwner", "(Ljava/lang/Object;)I", reinterpret_cast<void *>(LockOwner)},
    {"heapForLoader", "(Ljava/lang/ClassLoader;)[J", reinterpret_cast<void *>(HeapForLoader)},
    {"startNativeCaller", "(Ljava/lang/ThreadGroup;Ljava/lang/Class;Ljava/lang/String;Z)V",
     reinterpret_cast<void *>(StartNativeCaller)},
};

}  // namespace

extern "C" JNIEXPORT jint JNI_OnLoad(JavaVM *vm, void *) {
  gVm = vm;
  uintptr_t *libart_base = LibartHeapReferenceBase();
  if (libart_base != nullptr) art::mirror::gHeapReferenceBase = *libart_base;
  JNIEnv *env = nullptr;
  if (vm->GetEnv(reinterpret_cast<void **>(&env), JNI_VERSION_1_6) != JNI_OK) return JNI_ERR;
  jclass cls = env->FindClass("probe/Native");
  if (cls == nullptr) return JNI_ERR;
  if (env->RegisterNatives(cls, kMethods, sizeof(kMethods) / sizeof(kMethods[0])) != JNI_OK) return JNI_ERR;
  return JNI_VERSION_1_6;
}
