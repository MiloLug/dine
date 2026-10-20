#include "dinehello.h"

#include <string>
#include <vector>

// Exercises libc++ (std::string, std::vector, exceptions) so the smoke test
// proves the C++ runtime links into the Swift app, not just plain C.
const char *dine_hello(void) {
    static std::string msg = [] {
        std::vector<std::string> parts{"Hello", "from", "C++"};
        std::string s;
        for (const auto &p : parts) s += (s.empty() ? "" : " ") + p;
        try {
            throw std::string(" (libc++ ok, " __VERSION__ ")");
        } catch (const std::string &e) {
            s += e;
        }
        return s;
    }();
    return msg.c_str();
}
