// Dev builds only (CMake DINE_DEV): the multi-app phone probes (notes/multi-app-support/todo.md).
// Each runs on its own thread and logs `ma probe <name> <key> <value>`.

#include "dineart_dev.h"

#include <arpa/inet.h>
#include <dispatch/dispatch.h>
#include <errno.h>
#include <fcntl.h>
#include <mach/mach.h>
#include <malloc/malloc.h>
#include <netinet/in.h>
#include <os/log.h>
#include <os/proc.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/sysctl.h>
#include <time.h>
#include <unistd.h>

#include <atomic>
#include <string>
#include <vector>

namespace {

os_log_t Log() {
  static os_log_t log = os_log_create("dev.dine.Dine", "probe");
  return log;
}

void Out(const char *probe, const char *key, const std::string &value) {
  os_log(Log(), "ma probe %{public}s %{public}s %{public}s", probe, key, value.c_str());
}

std::string Errno(int err) { return std::to_string(err) + " " + strerror(err); }

uint64_t NowMs() {
  timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec * 1000ull + ts.tv_nsec / 1000000;
}

std::string Memory() {
  task_vm_info_data_t info{};
  mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
  kern_return_t kr = task_info(mach_task_self(), TASK_VM_INFO, reinterpret_cast<task_info_t>(&info), &count);
  if (kr != KERN_SUCCESS) return "task_info " + std::to_string(kr);
  return "footprint=" + std::to_string(info.phys_footprint >> 20) + "MB peak=" +
         std::to_string(info.ledger_phys_footprint_peak >> 20) + "MB limit-remaining=" +
         std::to_string(info.limit_bytes_remaining >> 20) + "MB available=" +
         std::to_string(os_proc_available_memory() >> 20) + "MB";
}

bool Pair(int *client, int *peer) {
  int server = socket(AF_INET, SOCK_STREAM, 0);
  sockaddr_in addr{};
  addr.sin_len = sizeof addr;
  addr.sin_family = AF_INET;
  addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  socklen_t len = sizeof addr;
  if (server < 0 || bind(server, reinterpret_cast<sockaddr *>(&addr), sizeof addr) != 0 || listen(server, 1) != 0 ||
      getsockname(server, reinterpret_cast<sockaddr *>(&addr), &len) != 0) {
    return false;
  }
  *client = socket(AF_INET, SOCK_STREAM, 0);
  if (connect(*client, reinterpret_cast<sockaddr *>(&addr), sizeof addr) != 0) return false;
  *peer = accept(server, nullptr, nullptr);
  close(server);
  return *peer >= 0;
}

struct Reader {
  int fd;
  std::atomic<bool> done{false};
  ssize_t result = 0;
  int err = 0;
  uint64_t end = 0;
};

void *ReadMain(void *arg) {
  auto *r = static_cast<Reader *>(arg);
  char c;
  r->result = read(r->fd, &c, 1);
  r->err = errno;
  r->end = NowMs();
  r->done = true;
  return nullptr;
}

bool WaitDone(const Reader &r, int ms) {
  for (int waited = 0; !r.done && waited < ms; waited += 10) usleep(10000);
  return r.done;
}

// What wakes a thread blocked in read() on a TCP socket.
void ShutdownRead() {
  for (const char *how : {"shutdown", "close"}) {
    int client = -1, peer = -1;
    if (!Pair(&client, &peer)) return Out("shutdown-read", how, "socket pair failed: " + Errno(errno));
    auto *r = new Reader{client};
    pthread_t thread;
    pthread_create(&thread, nullptr, ReadMain, r);
    usleep(200000);
    bool control = WaitDone(*r, 2000);
    uint64_t start = NowMs();
    if (strcmp(how, "shutdown") == 0) {
      shutdown(client, SHUT_RDWR);
    } else {
      close(client);
    }
    bool woke = WaitDone(*r, 3000);
    Out("shutdown-read", how,
        "control-woke=" + std::to_string(control) + " woke=" + std::to_string(woke) +
            (woke ? " ms=" + std::to_string(r->end - start) + " read=" + std::to_string(r->result) +
                        " errno=" + Errno(r->err)
                  : ""));
    // tests whether a reader still blocked returns once the peer closes
    close(peer);
    if (!woke) Out("shutdown-read", how, "after-peer-close woke=" + std::to_string(WaitDone(*r, 3000)));
    if (strcmp(how, "shutdown") == 0) close(client);
    if (r->done) {
      pthread_join(thread, nullptr);
      delete r;
    } else {
      pthread_detach(thread);
    }
  }
}

void Zones() {
  constexpr size_t kBlock = 4096, kCount = (64u << 20) / kBlock;
  std::vector<void *> blocks(kCount);
  auto fill = [&](malloc_zone_t *zone) {
    for (auto &b : blocks) {
      b = zone ? malloc_zone_malloc(zone, kBlock) : malloc(kBlock);
      memset(b, 1, kBlock);
    }
  };
  Out("zones", "before", Memory());
  malloc_zone_t *zone = malloc_create_zone(0, 0);
  // destroying the default zone would end Dine
  if (zone == nullptr || zone == malloc_default_zone()) {
    return Out("zones", "create", zone ? "returned the default zone" : "returned null");
  }
  malloc_set_zone_name(zone, "ma-probe");
  fill(zone);
  Out("zones", "zone-filled-64MB", Memory());
  for (auto b : blocks) malloc_zone_free(zone, b);
  Out("zones", "zone-freed", Memory());
  Out("zones", "zone-pressure-relief", std::to_string(malloc_zone_pressure_relief(zone, 0) >> 20) + "MB " + Memory());
  fill(zone);
  Out("zones", "zone-refilled", Memory());
  malloc_destroy_zone(zone);
  Out("zones", "zone-destroyed", Memory());
  fill(nullptr);
  Out("zones", "default-filled-64MB", Memory());
  for (auto b : blocks) free(b);
  Out("zones", "default-freed", Memory());
}

// ART releases pages with memset + MADV_DONTNEED on Apple (kMadviseZeroes is false).
void Madvise() {
  constexpr size_t kSize = 64u << 20;
  void *p = mmap(nullptr, kSize, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
  if (p == MAP_FAILED) return Out("madvise", "mmap", Errno(errno));
  Out("madvise", "mapped", Memory());
  memset(p, 1, kSize);
  Out("madvise", "touched-64MB", Memory());
  memset(p, 0, kSize);
  Out("madvise", "memset-0", Memory());
  int rc = madvise(p, kSize, MADV_DONTNEED);
  Out("madvise", "dontneed", "rc=" + std::to_string(rc) + " " + Memory());
  memset(p, 1, kSize);
  Out("madvise", "retouched", Memory());
  rc = madvise(p, kSize, MADV_FREE_REUSABLE);
  Out("madvise", "free-reusable", "rc=" + std::to_string(rc) + " " + Memory());
  munmap(p, kSize);
  Out("madvise", "unmapped", Memory());
}

// Whether a per-app zone could take over plain malloc: is the default zone's struct writable.
void DefaultZone() {
  malloc_zone_t *zone = malloc_default_zone();
  vm_address_t address = reinterpret_cast<vm_address_t>(zone);
  vm_size_t size = 0;
  vm_region_basic_info_data_64_t info{};
  mach_msg_type_number_t count = VM_REGION_BASIC_INFO_COUNT_64;
  mach_port_t object = MACH_PORT_NULL;
  kern_return_t kr = vm_region_64(mach_task_self(), &address, &size, VM_REGION_BASIC_INFO_64,
                                  reinterpret_cast<vm_region_info_t>(&info), &count, &object);
  Out("default-zone", "region",
      "kr=" + std::to_string(kr) + " name=" + (zone->zone_name ? zone->zone_name : "?") +
          " version=" + std::to_string(zone->version) + " prot=" + std::to_string(info.protection) +
          " max-prot=" + std::to_string(info.max_protection) +
          " contains=" + std::to_string(address <= reinterpret_cast<vm_address_t>(zone) &&
                                        reinterpret_cast<vm_address_t>(zone) < address + size));
  vm_address_t *zones = nullptr;
  unsigned zone_count = 0;
  kr = malloc_get_all_zones(mach_task_self(), nullptr, &zones, &zone_count);
  std::string names;
  for (unsigned i = 0; kr == KERN_SUCCESS && i < zone_count; i++) {
    auto *z = reinterpret_cast<malloc_zone_t *>(zones[i]);
    names += std::string(z->zone_name ? z->zone_name : "?") + " ";
  }
  Out("default-zone", "zones", "count=" + std::to_string(zone_count) + " " + names);
}

void Limits() {
  Out("limits", "memory", Memory());
  rlimit limit{};
  getrlimit(RLIMIT_NOFILE, &limit);
  auto text = [](rlim_t v) { return v == RLIM_INFINITY ? std::string("inf") : std::to_string(v); };
  Out("limits", "nofile", "soft=" + text(limit.rlim_cur) + " hard=" + text(limit.rlim_max));
  int per_proc = 0;
  size_t len = sizeof per_proc;
  int sysctl_rc = sysctlbyname("kern.maxfilesperproc", &per_proc, &len, nullptr, 0);
  Out("limits", "maxfilesperproc", sysctl_rc == 0 ? std::to_string(per_proc) : "sysctl " + Errno(errno));
  rlimit original = limit;
  rlimit raised = limit;
  raised.rlim_cur = limit.rlim_max != RLIM_INFINITY ? limit.rlim_max
                    : sysctl_rc == 0 && per_proc > 0 ? static_cast<rlim_t>(per_proc)
                                                      : limit.rlim_cur;
  int rc = setrlimit(RLIMIT_NOFILE, &raised);
  int err = errno;
  getrlimit(RLIMIT_NOFILE, &limit);
  Out("limits", "nofile-raised",
      "rc=" + std::to_string(rc) + (rc ? " errno=" + Errno(err) : "") + " soft=" + text(limit.rlim_cur));
  // Dine's other threads can't open anything while this holds every descriptor: keep it short
  std::vector<int> fds;
  int base = open("/dev/null", O_RDONLY);
  int fd = 0;
  while (fds.size() < 200000 && (fd = dup(base)) >= 0) fds.push_back(fd);
  err = errno;
  for (int open_fd : fds) close(open_fd);
  close(base);
  Out("limits", "opened", std::to_string(fds.size() + 1) + (fd < 0 ? " then errno=" + Errno(err) : " (cap)"));
  setrlimit(RLIMIT_NOFILE, &original);
}

std::atomic<uint64_t> gSpin;
std::atomic<bool> gSpinStop;

void *SpinMain(void *) {
  while (!gSpinStop.load(std::memory_order_relaxed)) gSpin.fetch_add(1, std::memory_order_relaxed);
  return nullptr;
}

bool Advancing(int ms) {
  uint64_t before = gSpin.load();
  usleep(ms * 1000);
  return gSpin.load() != before;
}

// Mach suspend and terminate on our own threads, the escalation for a thread that won't unwind.
void MachThreads() {
  gSpinStop = false;
  pthread_t spinner;
  pthread_create(&spinner, nullptr, SpinMain, nullptr);
  pthread_detach(spinner);
  mach_port_t port = pthread_mach_thread_np(spinner);
  bool running = Advancing(100);
  kern_return_t suspend = thread_suspend(port);
  usleep(1000);
  bool suspended = !Advancing(200);
  kern_return_t resume = thread_resume(port);
  bool resumed = Advancing(100);
  kern_return_t terminate = thread_terminate(port);
  usleep(1000);
  bool terminated = !Advancing(200);
  // a refused terminate would leave it spinning through the probes that follow
  gSpinStop = true;
  Out("mach-threads", "spinner",
      "running=" + std::to_string(running) + " suspend=" + std::to_string(suspend) + " stopped=" +
          std::to_string(suspended) + " resume=" + std::to_string(resume) + " resumed=" + std::to_string(resumed) +
          " terminate=" + std::to_string(terminate) + " gone=" + std::to_string(terminated));

  int client = -1, peer = -1;
  if (!Pair(&client, &peer)) return Out("mach-threads", "reader", "socket pair failed: " + Errno(errno));
  auto *r = new Reader{client};
  pthread_t reader;
  pthread_create(&reader, nullptr, ReadMain, r);
  pthread_detach(reader);
  usleep(200000);
  kern_return_t kr = thread_terminate(pthread_mach_thread_np(reader));
  usleep(100000);
  close(peer);
  usleep(200000);
  // the reader object leaks on purpose: a terminated thread never frees it
  Out("mach-threads", "reader-in-read", "terminate=" + std::to_string(kr) + " returned-after-fin=" +
                                            std::to_string(r->done.load()) + " " + Memory());
  close(client);
}

std::atomic<int> gJetsamFd{-1};

void JetsamLine(const std::string &line) {
  Out("jetsam", "step", line);
  int fd = gJetsamFd.load();
  if (fd < 0) return;
  std::string text = line + "\n";
  write(fd, text.data(), text.size());
  fsync(fd);
}

void OnPressure(void *context) {
  auto source = static_cast<dispatch_source_t>(context);
  JetsamLine("pressure " + std::to_string(dispatch_source_get_data(source)) + " " + Memory());
}

std::string JetsamFile() { return std::string(getenv("HOME")) + "/Library/Caches/ma-jetsam.txt"; }

// Touches 32 MB steps until iOS kills Dine. Each step goes to os_log and, with fsync, to
// JetsamFile, since the log lines just before a kill may be lost.
void Jetsam() {
  int fd = open(JetsamFile().c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_APPEND, 0644);
  gJetsamFd = fd;
  dispatch_queue_t queue = dispatch_queue_create("dev.dine.ma-probe.pressure", DISPATCH_QUEUE_SERIAL);
  dispatch_source_t source = dispatch_source_create(
      DISPATCH_SOURCE_TYPE_MEMORYPRESSURE, 0,
      DISPATCH_MEMORYPRESSURE_NORMAL | DISPATCH_MEMORYPRESSURE_WARN | DISPATCH_MEMORYPRESSURE_CRITICAL, queue);
  dispatch_set_context(source, source);
  dispatch_source_set_event_handler_f(source, OnPressure);
  dispatch_resume(source);
  constexpr size_t kStep = 32u << 20;
  JetsamLine("start " + Memory());
  for (size_t total = kStep;; total += kStep) {
    void *p = mmap(nullptr, kStep, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (p == MAP_FAILED) return JetsamLine("mmap failed at " + std::to_string(total >> 20) + "MB: " + Errno(errno));
    memset(p, 1, kStep);
    JetsamLine("touched=" + std::to_string(total >> 20) + "MB " + Memory());
    usleep(100000);
  }
}

void JetsamReport() {
  FILE *f = fopen(JetsamFile().c_str(), "r");
  if (f == nullptr) return Out("jetsam-report", "file", Errno(errno));
  std::vector<std::string> lines;
  char buf[512];
  while (fgets(buf, sizeof buf, f)) lines.emplace_back(buf, strcspn(buf, "\n"));
  fclose(f);
  Out("jetsam-report", "lines", std::to_string(lines.size()));
  for (const auto &line : lines) {
    if (line.rfind("pressure", 0) == 0) Out("jetsam-report", "line", line);
  }
  for (size_t i = lines.size() > 3 ? lines.size() - 3 : 0; i < lines.size(); i++) Out("jetsam-report", "line", lines[i]);
}

struct Probe {
  const char *name;
  void (*run)();
};

const Probe kProbes[] = {
    {"shutdown-read", ShutdownRead}, {"zones", Zones},   {"madvise", Madvise},         {"default-zone", DefaultZone},
    {"limits", Limits},              {"mach-threads", MachThreads}, {"jetsam", Jetsam}, {"jetsam-report", JetsamReport},
};

void *ProbeMain(void *arg) {
  auto *probe = static_cast<const Probe *>(arg);
  Out(probe->name, "start", "");
  probe->run();
  Out(probe->name, "done", "");
  return nullptr;
}

}  // namespace

int dine_ma_probe(const char *name) {
  for (const Probe &probe : kProbes) {
    if (strcmp(probe.name, name) != 0) continue;
    pthread_t thread;
    if (pthread_create(&thread, nullptr, ProbeMain, const_cast<Probe *>(&probe)) != 0) return -1;
    pthread_detach(thread);
    return 0;
  }
  os_log_error(Log(), "ma probe %{public}s: no such probe", name);
  return -1;
}
