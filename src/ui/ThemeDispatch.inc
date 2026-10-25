#include "ThemeRenderer.h"
#include <cstring>
extern SessionData g_Sessions[SessionIndex::INDEX_MAX];
extern uint32_t g_HeartbeatTimeout, g_Now;
extern bool g_PcAsleep;

namespace Display {
static uint8_t s_selectedDeviceTheme=0;
static uint8_t s_activeDeviceTheme=255;

bool SetDeviceTheme(uint8_t id) {
    if(id>7)return false;
    s_selectedDeviceTheme=id;
    return true;
}
uint8_t DeviceTheme() { return s_selectedDeviceTheme; }
uint8_t ActiveDeviceTheme() { return s_activeDeviceTheme; }
void Update() { ThemeUI::Tick();ClassicUpdate(); }

static void CopySession(ThemeUI::Session& target,const SessionData* source,bool available=true) {
    if(!source)return;
    std::memcpy(target.name,source->name,sizeof target.name);target.name[29]=0;
    target.volume=source->data.volume>100?100:source->data.volume;
    target.muted=source->data.isMuted;target.isDefault=source->data.isDefault;
    target.available=available&&target.name[0]!=0;
    if(!target.available){target.volume=0;target.muted=false;target.isDefault=false;}
}
static ThemeUI::ViewModel ThemeModel(ThemeUI::Page page,DisplayMode mode,SessionData* current=nullptr) {
    ThemeUI::ViewModel view;std::memset(&view,0,sizeof view);
    view.page=page;view.mode=uint8_t(mode);
    view.pcConnected=!g_PcAsleep&&g_HeartbeatTimeout!=0&&int32_t(g_HeartbeatTimeout-g_Now)>0;
    CopySession(view.current,current);CopySession(view.alternate,&g_Sessions[INDEX_ALTERNATE]);
    view.meterCurrent=s_meterCurrentValue;view.meterAlternate=s_meterAlternateValue;
    if(mode==MODE_APPLICATION) {
        view.mediaValid=g_MediaInfoValid;view.mediaPlaying=g_MediaInfo.isPlaying!=0;
        std::memcpy(view.mediaTitle,g_MediaInfo.title,sizeof view.mediaTitle);view.mediaTitle[31]=0;
        std::memcpy(view.mediaArtist,g_MediaInfo.artist,sizeof view.mediaArtist);view.mediaArtist[23]=0;
        view.mediaPosition=g_MediaInfo.positionSec;view.mediaDuration=g_MediaInfo.durationSec;
    }
    return view;
}
static void PrepareClassic() {
    if(ThemeUI::Exists()) { ThemeUI::Destroy();FullReset(); }
}
static bool RenderTheme(const ThemeUI::ViewModel& view) {
    if(s_selectedDeviceTheme==0)return false;
    if(!ThemeUI::Exists())FullReset();
    if(!ThemeUI::Render(s_selectedDeviceTheme,view)) {
        ThemeUI::Destroy();FullReset();s_activeDeviceTheme=255;return false;
    }
    s_activeDeviceTheme=s_selectedDeviceTheme;return true;
}
static void ClassicResult() { s_activeDeviceTheme=s_selectedDeviceTheme?255:0; }

void SplashScreen() {
    auto view=ThemeModel(ThemeUI::Page::Offline,MODE_SPLASH);
    if(RenderTheme(view))return;
    PrepareClassic();ClassicSplashScreen();ClassicResult();
}
void KeyTestScreen() {
    PrepareClassic();ClassicKeyTestScreen();s_activeDeviceTheme=s_selectedDeviceTheme;
}
void InfoScreen(bool touchAvailable) {
    PrepareClassic();ClassicInfoScreen(touchAvailable);s_activeDeviceTheme=s_selectedDeviceTheme;
}
void ClockScreen(uint8_t hour,uint8_t minute,uint8_t second) {
    PrepareClassic();OriginalClockScreen(hour,minute,second);s_activeDeviceTheme=255;
}
static ThemeUI::ViewModel Selection(SessionData* session,bool left,bool right,DisplayMode mode,char channel=0) {
    auto view=ThemeModel(ThemeUI::Page::Select,mode,session);view.canPrevious=left;view.canNext=right;view.selectChannel=channel;
    CopySession(view.previous,&g_Sessions[INDEX_PREVIOUS],left);CopySession(view.next,&g_Sessions[INDEX_NEXT],right);
    return view;
}
void DeviceSelectScreen(SessionData* session,bool left,bool right,DisplayMode mode) {
    if(RenderTheme(Selection(session,left,right,mode)))return;
    PrepareClassic();ClassicDeviceSelectScreen(session,left,right,mode);ClassicResult();
}
void DeviceEditScreen(SessionData* session,const char* label,DisplayMode mode) {
    if(RenderTheme(ThemeModel(ThemeUI::Page::Audio,mode,session)))return;
    PrepareClassic();ClassicDeviceEditScreen(session,label,mode);ClassicResult();
}
void ApplicationSelectScreen(SessionData* session,bool left,bool right,DisplayMode mode) {
    if(RenderTheme(Selection(session,left,right,mode)))return;
    PrepareClassic();ClassicApplicationSelectScreen(session,left,right,mode);ClassicResult();
}
void ApplicationEditScreen(SessionData* session,DisplayMode mode) {
    if(RenderTheme(ThemeModel(ThemeUI::Page::Audio,mode,session)))return;
    PrepareClassic();ClassicApplicationEditScreen(session,mode);ClassicResult();
}
void GameSelectScreen(SessionData* session,char channel,bool left,bool right,DisplayMode mode) {
    if(RenderTheme(Selection(session,left,right,mode,channel)))return;
    PrepareClassic();ClassicGameSelectScreen(session,channel,left,right,mode);ClassicResult();
}
void GameEditScreen(SessionData* alternate,SessionData* current,DisplayMode mode) {
    auto view=ThemeModel(ThemeUI::Page::Game,mode,current);CopySession(view.alternate,alternate);
    if(RenderTheme(view))return;
    PrepareClassic();ClassicGameEditScreen(alternate,current,mode);ClassicResult();
}
void HealthScreen(bool pcConnected,uint32_t uptimeSeconds,uint32_t serialAgeMs,uint32_t freeHeap,
    uint32_t minFreeHeap,uint32_t maxAllocHeap,uint32_t rxFrames,uint32_t txFrames,uint32_t crcErrors,
    uint32_t protocolErrors,Command lastCommand,Command lastErrorCommand,uint8_t currentMode,uint8_t currentIndex,
    uint8_t outputCount,uint8_t inputCount,uint8_t appCount,bool touchReady,uint32_t touchSamples) {
    auto view=ThemeModel(ThemeUI::Page::Health,MODE_HEALTH);
    view.pcConnected=pcConnected;view.serialAgeMs=serialAgeMs;view.freeHeap=freeHeap;view.rxFrames=rxFrames;
    view.statsValid=g_PcStatsValid;view.cpu=g_PcStats.cpuUsage;view.cpuTemp=g_PcStats.cpuTemp;
    view.gpu=g_PcStats.gpuUsage;view.gpuTemp=g_PcStats.gpuTemp;view.ram=g_PcStats.ramUsage;
    view.ramUsedMB=g_PcStats.ramUsedMB;view.ramTotalMB=g_PcStats.ramTotalMB;
    view.netDownKBps=g_PcStats.netDownKBps;view.netUpKBps=g_PcStats.netUpKBps;
    if(RenderTheme(view))return;
    PrepareClassic();ClassicHealthScreen(pcConnected,uptimeSeconds,serialAgeMs,freeHeap,minFreeHeap,maxAllocHeap,
        rxFrames,txFrames,crcErrors,protocolErrors,lastCommand,lastErrorCommand,currentMode,currentIndex,
        outputCount,inputCount,appCount,touchReady,touchSamples);ClassicResult();
}
} // namespace Display
