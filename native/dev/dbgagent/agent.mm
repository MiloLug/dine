// In-app debug agent behind `tools/dine dbg ui …`: UI work without lldb or the host's accessibility
// inspector. One request line, one JSON reply line per connection:
//   ls               {"labels": [[isElement, label], …]} of the key window's accessibility walk
//   tap N "LABEL"    activates element N of the last walk if it still has LABEL (a JSON string): its
//                    accessibilityActivate, else a control's tap events, else the alert action with
//                    that title; replies before the activation runs, so a breakpoint it hits can't
//                    block the reply
//   type N ["LABEL", "TEXT"]  makes element N of the last walk the first responder if it still has
//                    LABEL and edits text, then inserts TEXT as a keyboard does; also run after the
//                    reply
//   back             accessibility escape (VoiceOver's back gesture), also run after the reply
//   action "NAME"    the first accessibility custom action named NAME up from the walk, as back
//                    searches; also run after the reply
//   settle MS        waits until the last tap/back ran, no transition runs and the labels hold still,
//                    or MS pass (at most 10 s): {"labels", "settled", "ran",
//                    "result": tap's or action's BOOL (action: null when none has the name), or
//                    back's handler class or null}
// Anything else closes the connection unanswered.

#import <UIKit/UIKit.h>
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <objc/message.h>
#include <os/log.h>
#include <pthread.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include "dbgagent.h"

namespace {

os_log_t Log() {
  static os_log_t log = os_log_create("dev.dine.Dine", "dbgagent");
  return log;
}

// Main thread only.
NSArray *gItems;   // elements of the last walk
NSArray *gLabels;  // their [isElement, label] pairs
NSArray *gBefore;  // gLabels when the last tap/back was asked for
id gResult;        // nil until that tap/back ran; back without a handler: NSNull

void OnMain(void (^block)(void)) { dispatch_sync(dispatch_get_main_queue(), block); }

UIWindow *KeyWindow() {
  for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
    if (![scene isKindOfClass:UIWindowScene.class]) continue;
    for (UIWindow *window in ((UIWindowScene *)scene).windows)
      if (window.isKeyWindow) return window;
  }
  return nil;
}

// Accessibility elements and subviews, depth first, each object once, skipping what VoiceOver can't
// reach: hidden subtrees and elements off screen (a pushed-over screen stays in the hierarchy). A
// getter that throws (SwiftUI's _UIButtonBarButton does) only skips that element.
void Walk() {
  NSMutableArray *items = [NSMutableArray array], *labels = [NSMutableArray array];
  NSHashTable *seen = [NSHashTable hashTableWithOptions:NSPointerFunctionsObjectPointerPersonality];
  NSMutableArray *stack = [NSMutableArray array];
  UIWindow *window = KeyWindow();
  CGRect screen = window.screen.bounds;
  if (window) [stack addObject:window];
  while (stack.count && seen.count < 5000) {
    id e = stack.lastObject;
    [stack removeLastObject];
    if ([seen containsObject:e]) continue;
    [seen addObject:e];
    if ([e isKindOfClass:UIView.class] && (((UIView *)e).hidden || ((UIView *)e).alpha < 0.01)) continue;
    @try {
      if ([e accessibilityElementsHidden]) continue;
      NSString *label = [e accessibilityLabel];
      if ([label isKindOfClass:NSString.class] && label.length &&
          !CGRectIsEmpty(CGRectIntersection([e accessibilityFrame], screen))) {
        [items addObject:e];
        [labels addObject:@[@([e isAccessibilityElement]), label]];
      }
      NSArray *children = [e accessibilityElements];
      if ([children isKindOfClass:NSArray.class]) [stack addObjectsFromArray:children];
    } @catch (NSException *) {
    }
    if ([e isKindOfClass:UIView.class]) [stack addObjectsFromArray:((UIView *)e).subviews];
  }
  gItems = items;
  gLabels = labels;
}

bool Transitioning(UIViewController *vc) {
  if (!vc) return false;
  if (vc.transitionCoordinator) return true;
  for (UIViewController *child in vc.childViewControllers)
    if (Transitioning(child)) return true;
  return Transitioning(vc.presentedViewController);
}

// Where back and action climb from: the walked elements, last first (content comes last in the walk,
// the nav bar is a sibling above it), then the presented controllers' views, top first, for screens
// without labels (an alert's chain skips the view it is presented over).
NSArray *ClimbStarts() {
  NSMutableArray *starts = [gItems.reverseObjectEnumerator.allObjects mutableCopy];
  NSUInteger end = starts.count;
  for (UIViewController *vc = KeyWindow().rootViewController; vc; vc = vc.presentedViewController)
    if (vc.view) [starts insertObject:vc.view atIndex:end];
  return starts;
}

// Up through containers and responders; a navigation controller pops.
id Escape() {
  for (id start in ClimbStarts()) {
    id c = start;
    for (int k = 0; c && k < 40; k++) {
      id up = nil;
      @try {
        if ([c accessibilityPerformEscape]) return NSStringFromClass([c class]);
        up = [c accessibilityContainer];
      } @catch (NSException *) {
      }
      c = up ?: ([c respondsToSelector:@selector(nextResponder)] ? [c nextResponder] : nil);
    }
  }
  return NSNull.null;
}

id RunAction(NSString *name) {
  for (id start in ClimbStarts()) {
    id c = start;
    for (int k = 0; c && k < 40; k++) {
      id up = nil;
      @try {
        for (UIAccessibilityCustomAction *action in [c accessibilityCustomActions]) {
          if (![action.name isEqualToString:name]) continue;
          if (action.actionHandler) return @(action.actionHandler(action));
          return @(((BOOL (*)(id, SEL, id))objc_msgSend)(action.target, action.selector, action));
        }
        up = [c accessibilityContainer];
      } @catch (NSException *) {
      }
      c = up ?: ([c respondsToSelector:@selector(nextResponder)] ? [c nextResponder] : nil);
    }
  }
  return NSNull.null;
}

void Reply(int fd, NSDictionary *obj) {
  NSMutableData *data = [[NSJSONSerialization dataWithJSONObject:obj options:0 error:nil] mutableCopy];
  [data appendBytes:"\n" length:1];
  for (size_t off = 0; off < data.length;) {
    ssize_t n = send(fd, (const char *)data.bytes + off, data.length - off, 0);
    if (n <= 0) return;
    off += (size_t)n;
  }
}

NSString *ReadLine(int fd) {
  char buf[4096];
  for (size_t n = 0; n < sizeof buf; n++) {
    if (recv(fd, buf + n, 1, 0) != 1) return nil;
    if (buf[n] == '\n') return [[NSString alloc] initWithBytes:buf length:n encoding:NSUTF8StringEncoding];
  }
  return nil;
}

// UIKit controls decline accessibilityActivate too (VoiceOver touches them): send what a tap sends.
// One mask, so an action registered for both events runs once.
BOOL ActivateControl(id item) {
  if (![item isKindOfClass:UIControl.class] || !((UIControl *)item).enabled) return NO;
  [(UIControl *)item sendActionsForControlEvents:UIControlEventTouchUpInside | UIControlEventPrimaryActionTriggered];
  return YES;
}

// UIAlertController's action views decline accessibilityActivate (VoiceOver touches their activation
// point instead), so the topmost alert's enabled action with that title runs as a tap runs it: the
// alert dismisses, then the handler (private, through KVC) runs.
BOOL ActivateAlertAction(NSString *label) {
  UIViewController *top = KeyWindow().rootViewController;
  while (top.presentedViewController) top = top.presentedViewController;
  if (![top isKindOfClass:UIAlertController.class] || top.isBeingDismissed) return NO;
  for (UIAlertAction *action in ((UIAlertController *)top).actions) {
    if (!action.enabled || ![action.title isEqualToString:label]) continue;
    void (^handler)(UIAlertAction *) = nil;
    @try {
      handler = [action valueForKey:@"handler"];
    } @catch (NSException *) {
    }
    [top.presentingViewController dismissViewControllerAnimated:YES completion:^{
      if (handler) handler(action);
    }];
    return YES;
  }
  return NO;
}

void Tap(int fd, NSInteger n, NSString *label) {
  __block BOOL ok = NO;
  OnMain(^{
    if (n < 0 || n >= (NSInteger)gLabels.count || ![gLabels[n][1] isEqualToString:label]) return;
    ok = YES;
    id item = gItems[n];
    gBefore = gLabels;
    gResult = nil;
    dispatch_async(dispatch_get_main_queue(), ^{
      gResult = @([item accessibilityActivate] || ActivateControl(item) || ActivateAlertAction(label));
    });
  });
  Reply(fd, ok ? @{@"ok": @YES} : @{@"error": @"the screen changed since the last ls"});
}

void Type(int fd, NSInteger n, NSString *label, NSString *text) {
  __block BOOL ok = NO;
  OnMain(^{
    if (n < 0 || n >= (NSInteger)gLabels.count || ![gLabels[n][1] isEqualToString:label]) return;
    ok = YES;
    id item = gItems[n];
    gBefore = gLabels;
    gResult = nil;
    dispatch_async(dispatch_get_main_queue(), ^{
      BOOL typed = [item isKindOfClass:UIResponder.class] && [item conformsToProtocol:@protocol(UITextInput)] &&
                   ([item isFirstResponder] || [item becomeFirstResponder]);
      if (typed) [(id<UITextInput>)item insertText:text];
      gResult = @(typed);
    });
  });
  Reply(fd, ok ? @{@"ok": @YES} : @{@"error": @"the screen changed since the last ls"});
}

void Action(int fd, NSString *name) {
  OnMain(^{
    Walk();
    gBefore = gLabels;
    gResult = nil;
    dispatch_async(dispatch_get_main_queue(), ^{ gResult = RunAction(name); });
  });
  Reply(fd, @{@"ok": @YES});
}

void Back(int fd) {
  OnMain(^{
    Walk();
    gBefore = gLabels;
    gResult = nil;
    dispatch_async(dispatch_get_main_queue(), ^{ gResult = Escape(); });
  });
  Reply(fd, @{@"ok": @YES});
}

// The minimum wait when the screen looks unchanged: a push can start a frame or two after the
// activation.
void Settle(int fd, NSInteger ms) {
  CFAbsoluteTime start = CFAbsoluteTimeGetCurrent();
  __block NSArray *labels = nil, *before = nil;
  __block id result = nil;
  __block BOOL moving = NO;
  NSArray *prev = nil;
  BOOL settled = NO;
  for (;;) {
    OnMain(^{
      Walk();
      labels = gLabels;
      before = gBefore;
      result = gResult;
      moving = Transitioning(KeyWindow().rootViewController);
    });
    CFAbsoluteTime elapsed = CFAbsoluteTimeGetCurrent() - start;
    if (result && !moving && [labels isEqual:prev] && (![labels isEqual:before] || elapsed >= 0.3)) {
      settled = YES;
      break;
    }
    if (elapsed * 1000 >= ms) break;
    prev = labels;
    usleep(100000);
  }
  Reply(fd, @{@"labels": labels ?: @[], @"settled": @(settled), @"ran": @(result != nil),
              @"result": result ?: NSNull.null});
}

bool Digits(NSString *s) {
  return s.length > 0 && s.length < 9 &&
         [s rangeOfCharacterFromSet:NSCharacterSet.decimalDigitCharacterSet.invertedSet].location == NSNotFound;
}

void Handle(int fd) {
  NSString *line = ReadLine(fd);
  NSArray<NSString *> *words = [line componentsSeparatedByString:@" "];
  if ([line isEqualToString:@"ls"]) {
    __block NSArray *labels;
    OnMain(^{
      Walk();
      labels = gLabels;
    });
    Reply(fd, @{@"labels": labels});
  } else if ([line isEqualToString:@"back"]) {
    Back(fd);
  } else if (words.count == 2 && [words[0] isEqualToString:@"settle"] && Digits(words[1])) {
    Settle(fd, MIN(words[1].integerValue, 10000));
  } else if (words.count >= 2 && [words[0] isEqualToString:@"action"]) {
    NSString *json = [[words subarrayWithRange:NSMakeRange(1, words.count - 1)] componentsJoinedByString:@" "];
    id name = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding]
                                              options:NSJSONReadingFragmentsAllowed
                                                error:nil];
    if ([name isKindOfClass:NSString.class]) Action(fd, name);
  } else if (words.count >= 3 && [words[0] isEqualToString:@"tap"] && Digits(words[1])) {
    NSString *json = [[words subarrayWithRange:NSMakeRange(2, words.count - 2)] componentsJoinedByString:@" "];
    id label = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding]
                                               options:NSJSONReadingFragmentsAllowed
                                                 error:nil];
    if ([label isKindOfClass:NSString.class]) Tap(fd, words[1].integerValue, label);
  } else if (words.count >= 3 && [words[0] isEqualToString:@"type"] && Digits(words[1])) {
    NSString *json = [[words subarrayWithRange:NSMakeRange(2, words.count - 2)] componentsJoinedByString:@" "];
    id pair = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    if ([pair isKindOfClass:NSArray.class] && [pair count] == 2 && [pair[0] isKindOfClass:NSString.class] &&
        [pair[1] isKindOfClass:NSString.class])
      Type(fd, words[1].integerValue, pair[0], pair[1]);
  }
}

void *Serve(void *arg) {
  int port = (int)(intptr_t)arg;
  int fd = socket(AF_INET, SOCK_STREAM, 0);
  int one = 1;
  setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
  sockaddr_in addr = {};
  addr.sin_len = sizeof addr;
  addr.sin_family = AF_INET;
  addr.sin_port = htons((uint16_t)port);
  addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (bind(fd, (sockaddr *)&addr, sizeof addr) != 0 || listen(fd, 8) != 0) {
    os_log_error(Log(), "dbg agent: can't listen on 127.0.0.1:%d: %{public}s", port, strerror(errno));
    close(fd);
    return nullptr;
  }
  os_log(Log(), "dbg agent listening on 127.0.0.1:%d", port);
  for (;;) {
    int c = accept(fd, nullptr, nullptr);
    if (c < 0) {
      if (errno == EINTR || errno == ECONNABORTED) continue;
      os_log_error(Log(), "dbg agent: accept: %{public}s", strerror(errno));
      return nullptr;
    }
    setsockopt(c, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof one);
    timeval timeout = {5, 0};
    setsockopt(c, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
    setsockopt(c, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout);
    @autoreleasepool {
      Handle(c);
    }
    close(c);
  }
}

}  // namespace

void dine_dbg_agent_start(void) {
  const char *env = getenv("DINE_DBG_AGENT_PORT");
  int port = env ? atoi(env) : 0;
  if (port <= 0) return;
  pthread_t thread;
  if (pthread_create(&thread, nullptr, Serve, (void *)(intptr_t)port) == 0) pthread_detach(thread);
}
