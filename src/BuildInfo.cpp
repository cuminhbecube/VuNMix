#include "Config.h"

// Keep release/build metadata in the firmware image even when section garbage
// collection is enabled. scripts/build_metadata.py forces this external symbol
// as an undefined linker root, so the section cannot be discarded.
extern "C"
{
    extern const char VUNMIX_BUILD_METADATA[] =
        "VuNMixBuild:" VERSION ";G=" VUNMIX_GIT_SHA ";B=" VUNMIX_BUILD_DATE;
}
