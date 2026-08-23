#include "Config.h"

// Keep release/build metadata in the firmware image even when link-time
// optimization is enabled. This lets CI verify that the binary really contains
// the same version/SHA/date that was used to package the release.
extern "C"
{
    __attribute__((used)) const char VUNMIX_BUILD_METADATA[] =
        "VuNMixBuild:" VERSION ";G=" VUNMIX_GIT_SHA ";B=" VUNMIX_BUILD_DATE;
}
