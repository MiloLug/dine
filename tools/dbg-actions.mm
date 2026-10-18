// Debug actions: `tools/dine dbg` defines this file into the app once per process (lldb
// `expression --top-level`, ObjC++) and calls it on the paused main thread (`ui tap|back`, `dbg call`).
// lldb's rules for it:
// - Callables are `extern "C"` with the signature on one line: the server declares them to each call
//   from that line, since lldb itself can't see functions whose bodies send ObjC messages.
// - No `static`: lldb re-emits other bodies into each call, and that copy can't link to a static.
// - No class names or @"" literals (lldb then reads every class name, ~35 s): objc_getClass.
//   No `nil`: lldb resolves it to some library's symbol of that name; use 0.
// - No @try (lldb compiles without ObjC exceptions). `dine_` on every name: bare ones clash with
//   system symbols.

id dine_cls(const char *name) { return ((id (*)(const char *))objc_getClass)(name); }
const char *dine_cname(id o) { return ((const char *(*)(id))object_getClassName)(o); }
id dine_nsstr(const char *s) {
  return ((id (*)(id, SEL, const char *))objc_msgSend)(dine_cls("NSString"), @selector(stringWithUTF8String:), s);
}

// Elements of the last `dine_ui_collect`, indexed by `dine_ui_activate`.
id dine_ui_items;
// The element whose accessibility getters are running: when one throws, the call aborts and the
// server skips this element's class.
id dine_ui_last;

// `flag label` per labelled element, joined by \x1e; flag 1 = isAccessibilityElement. `skip`: class
// names, comma-separated, whose AX getters aren't called.
extern "C" id dine_ui_collect(const char *skip) {
  id dine_skip = (id)[dine_nsstr(skip) componentsSeparatedByString:dine_nsstr(",")];
  id dine_win = 0;
  for (id dine_s in (id)[(id)[dine_cls("UIApplication") sharedApplication] connectedScenes])
    for (id dine_w in (id)[dine_s windows]) if ((BOOL)[dine_w isKeyWindow]) dine_win = dine_w;
  id dine_stack = (id)[dine_cls("NSMutableArray") array];
  if (dine_win) (void)[dine_stack addObject:dine_win];
  (void)[dine_ui_items release];
  dine_ui_items = (id)[(id)[dine_cls("NSMutableArray") alloc] init];
  id dine_out = (id)[dine_cls("NSMutableArray") array];
  id dine_str = dine_cls("NSString"), dine_arr = dine_cls("NSArray"), dine_view = dine_cls("UIView");
  for (int dine_n = 0; (unsigned long)[dine_stack count] > 0 && dine_n < 5000; dine_n++) {
    id dine_e = (id)[dine_stack lastObject];
    (void)[dine_stack removeLastObject];
    dine_ui_last = dine_e;
    BOOL dine_ax = !(BOOL)[dine_skip containsObject:dine_nsstr(dine_cname(dine_e))];
    if (dine_ax && (BOOL)[dine_e respondsToSelector:@selector(accessibilityLabel)]) {
      id dine_l = (id)[dine_e accessibilityLabel];
      if (dine_l != 0 && (BOOL)[dine_l isKindOfClass:dine_str] && (unsigned long)[dine_l length] > 0) {
        (void)[dine_ui_items addObject:dine_e];
        id dine_flag = dine_nsstr((BOOL)[dine_e isAccessibilityElement] ? "1" : "0");
        (void)[dine_out addObject:(id)[dine_flag stringByAppendingString:dine_l]];
      }
    }
    if (dine_ax && (BOOL)[dine_e respondsToSelector:@selector(accessibilityElements)]) {
      id dine_a = (id)[dine_e accessibilityElements];
      if (dine_a != 0 && (BOOL)[dine_a isKindOfClass:dine_arr]) (void)[dine_stack addObjectsFromArray:dine_a];
    }
    if ((BOOL)[dine_e isKindOfClass:dine_view]) (void)[dine_stack addObjectsFromArray:(id)[dine_e subviews]];
  }
  dine_ui_last = 0;
  return (id)[dine_out componentsJoinedByString:dine_nsstr("\x1e")];
}

extern "C" const char *dine_ui_last_class(void) { return dine_ui_last ? dine_cname(dine_ui_last) : 0; }

extern "C" BOOL dine_ui_activate(long i) {
  return (BOOL)[(id)[dine_ui_items objectAtIndex:(unsigned long)i] accessibilityActivate];
}

// Accessibility escape (VoiceOver's back gesture) from the collected elements up their containers and
// responders; a navigation controller pops. Content elements come last in the walk (the nav bar is a
// sibling above them), so start there. Returns the class that handled it, or NULL.
extern "C" const char *dine_ui_escape(void) {
  for (long dine_i = (long)[dine_ui_items count] - 1; dine_i >= 0; dine_i--) {
    id dine_c = (id)[dine_ui_items objectAtIndex:(unsigned long)dine_i];
    for (int dine_k = 0; dine_c != 0 && dine_k < 40; dine_k++) {
      if ((BOOL)[dine_c respondsToSelector:@selector(accessibilityPerformEscape)] && (BOOL)[dine_c accessibilityPerformEscape])
        return dine_cname(dine_c);
      if ((BOOL)[dine_c respondsToSelector:@selector(accessibilityContainer)] && (id)[dine_c accessibilityContainer] != 0)
        dine_c = (id)[dine_c accessibilityContainer];
      else if ((BOOL)[dine_c respondsToSelector:@selector(nextResponder)])
        dine_c = (id)[dine_c nextResponder];
      else
        dine_c = 0;
    }
  }
  return 0;
}
