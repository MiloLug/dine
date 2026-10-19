#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// Serves `tools/dine dbg ui …` on 127.0.0.1:$DINE_DBG_AGENT_PORT; does nothing when the variable is
// unset (`tools/dine ios launch` sets it).
void dine_dbg_agent_start(void);

#ifdef __cplusplus
}
#endif
