#ifndef ARTBRIDGE_JNI_SYMBOLS_H
#define ARTBRIDGE_JNI_SYMBOLS_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// A linked JNI library's Java_* names (tools/libexec/jni-symbols.sh writes the table).
struct dine_jni_symbols {
  const char *library;  // its JNI_OnLoad_<library> stem
  const char *const *names;
  size_t count;
};

extern const struct dine_jni_symbols dine_jni_symbols[];
extern const size_t dine_jni_symbols_count;

#ifdef __cplusplus
}
#endif

#endif
