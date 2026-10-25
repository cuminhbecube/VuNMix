#include "ThemeRenderer.h"
#include "ThemeLogo.h"
#include <lvgl.h>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <initializer_list>

LV_FONT_DECLARE(lv_font_vn_14);

namespace ThemeUI {
static lv_obj_t* s_root = nullptr;
static ViewModel m{};
static uint8_t s_theme = 0;
static lv_draw_ctx_t* s_draw = nullptr;
static lv_area_t s_origin{};
static lv_area_t s_scrollAreas[2]{};
static uint8_t s_scrollCount=0;
static uint32_t s_scrollStarted=0,s_scrollUpdated=0;
static char s_mediaText[80]{};

// All primitive coordinates are local to the owned 320x240 draw object. The
// global LVGL screen and default theme are never restyled by this renderer.
namespace v {
inline bool is(const char* a,const char* b) { return std::strcmp(a,b)==0; }
static const lv_font_t *f12=&lv_font_montserrat_12,*f14=&lv_font_montserrat_14,
    *f16=&lv_font_montserrat_16,*f20=&lv_font_montserrat_20,*f24=&lv_font_montserrat_24,
    *f28=&lv_font_montserrat_28,*f36=&lv_font_montserrat_36,*f48=&lv_font_montserrat_48,
    *vn14=&lv_font_vn_14,*mono=&lv_font_unscii_16;

static const char* fmt(const char* format, unsigned a=0, unsigned b=0, unsigned c=0) {
    // Draw calls consume the text synchronously; no LVGL object retains it.
    static char buffers[8][80]; static uint8_t cursor=0;
    char* out=buffers[cursor++%8]; std::snprintf(out,80,format,a,b,c);return out;
}
static const char* decimal(uint16_t value, const char* suffix="") {
    static char buffers[4][32]; static uint8_t cursor=0;
    char* out=buffers[cursor++%4];
    std::snprintf(out,32,"%.1f%s",value/1024.0,suffix);
    return out;
}
static int clamp(int n) { return n<0?0:n>100?100:n; }
static void box(lv_obj_t*,int x,int y,int w,int h,uint32_t color,int radius=0) {
    if(w<=0||h<=0)return;
    lv_area_t area={lv_coord_t(s_origin.x1+x),lv_coord_t(s_origin.y1+y),
                    lv_coord_t(s_origin.x1+x+w-1),lv_coord_t(s_origin.y1+y+h-1)};
    lv_draw_rect_dsc_t d;lv_draw_rect_dsc_init(&d);
    d.bg_color=lv_color_hex(color);d.bg_opa=LV_OPA_COVER;d.radius=radius;
    d.border_width=0;d.shadow_width=0;
    lv_draw_rect(s_draw,&d,&area);
}
static void reset(lv_obj_t* p,uint32_t color) { box(p,0,0,320,240,color); }
static size_t copyUtf8(char* out,size_t capacity,const char* source) {
    size_t i=0,o=0;
    while(source&&source[i]&&o+1<capacity) {
        unsigned char ch=static_cast<unsigned char>(source[i]);
        size_t n=ch<0x80?1:(ch&0xe0)==0xc0?2:(ch&0xf0)==0xe0?3:(ch&0xf8)==0xf0?4:0;
        bool valid=n!=0;
        for(size_t j=1;valid&&j<n;j++)
            valid=source[i+j]&&((static_cast<unsigned char>(source[i+j])&0xc0)==0x80);
        if(!valid) { out[o++]='?';++i;continue; }
        if(o+n>=capacity)break;
        if(n==1&&(ch=='\n'||ch=='\r'||ch=='\t'))out[o++]=' ';
        else { std::memcpy(out+o,source+i,n);o+=n; }
        i+=n;
    }
    out[o]=0;return o;
}
static int textWidth(const char* text,const lv_font_t* font) {
    lv_point_t size{};lv_txt_get_size(&size,text,font,0,0,LV_COORD_MAX,LV_TEXT_FLAG_NONE);return size.x;
}
static void text(lv_obj_t*,int x,int y,int w,const char* value,const lv_font_t* font,
                 uint32_t ink,lv_text_align_t align=LV_TEXT_ALIGN_LEFT) {
    char rendered[100];size_t len=copyUtf8(rendered,sizeof rendered,value);
    int measured=textWidth(rendered,font);
    bool scroll=measured>w&&m.page==Page::Audio&&
        ((value==m.current.name&&m.mode<=2&&m.current.isDefault)||
         (value==s_mediaText&&m.mode==3&&m.mediaValid));
    if(measured>w&&!scroll) {
        do {
            if(!len)break;
            --len;while(len&&(static_cast<unsigned char>(rendered[len])&0xc0)==0x80)--len;
            rendered[len]=0;
        } while(len&&textWidth(rendered,font)+textWidth("...",font)>w);
        if(w>=textWidth("...",font))std::strcpy(rendered+len,"...");
    }
    lv_area_t area={lv_coord_t(s_origin.x1+x),lv_coord_t(s_origin.y1+y),
                    lv_coord_t(s_origin.x1+x+w-1),lv_coord_t(s_origin.y1+y+font->line_height-1)};
    lv_draw_label_dsc_t d;lv_draw_label_dsc_init(&d);
    d.font=font;d.color=lv_color_hex(ink);d.align=align;d.flag=LV_TEXT_FLAG_NONE;
    if(scroll) {
        bool known=false;for(uint8_t i=0;i<s_scrollCount;i++)
            if(std::memcmp(&s_scrollAreas[i],&area,sizeof area)==0)known=true;
        if(!known&&s_scrollCount<2)s_scrollAreas[s_scrollCount++]=area;
    }
    const lv_area_t* priorClip=s_draw->clip_area;lv_area_t clip;
    if(!_lv_area_intersect(&clip,priorClip,&area))return;
    s_draw->clip_area=&clip;
    if(scroll) {
        uint32_t cycle=900U+uint32_t((measured+24)*1000/28);
        uint32_t elapsed=uint32_t(lv_tick_get()-s_scrollStarted)%cycle;
        int offset=elapsed<900?0:int((elapsed-900)*28/1000);
        d.align=LV_TEXT_ALIGN_LEFT;d.flag=LV_TEXT_FLAG_EXPAND;
        area.x1-=offset;area.x2=area.x1+measured-1;
        lv_draw_label(s_draw,&d,&area,rendered,nullptr);
        area.x1+=measured+24;area.x2+=measured+24;
        lv_draw_label(s_draw,&d,&area,rendered,nullptr);
    } else lv_draw_label(s_draw,&d,&area,rendered,nullptr);
    s_draw->clip_area=priorClip;
}
static void line(lv_obj_t*,int x1,int y1,int x2,int y2,uint32_t color,int width=1) {
    lv_point_t a={lv_coord_t(s_origin.x1+x1),lv_coord_t(s_origin.y1+y1)};
    lv_point_t b={lv_coord_t(s_origin.x1+x2),lv_coord_t(s_origin.y1+y2)};
    lv_draw_line_dsc_t d;lv_draw_line_dsc_init(&d);
    d.color=lv_color_hex(color);d.width=width;d.round_start=1;d.round_end=1;
    lv_draw_line(s_draw,&d,&a,&b);
}
static void logo(lv_obj_t*,int x,int y,bool big=false) {
    const lv_img_dsc_t* source=big?&vunmix_logo_48:&vunmix_logo_20;
    lv_area_t area={lv_coord_t(s_origin.x1+x),lv_coord_t(s_origin.y1+y),
                    lv_coord_t(s_origin.x1+x+source->header.w-1),lv_coord_t(s_origin.y1+y+source->header.h-1)};
    lv_draw_img_dsc_t d;lv_draw_img_dsc_init(&d);lv_draw_img(s_draw,&d,&area,source);
}
static void bar(lv_obj_t* p,int x,int y,int w,int h,int value,uint32_t track,uint32_t ink,int radius=0) {
    box(p,x,y,w,h,track,radius);box(p,x,y,(w*clamp(value)+50)/100,h,ink,radius);
}
static void arc(lv_obj_t*,int x,int y,int size,int value,uint32_t track,uint32_t ink,int width=8) {
    lv_point_t center={lv_coord_t(s_origin.x1+x+size/2),lv_coord_t(s_origin.y1+y+size/2)};
    lv_draw_arc_dsc_t d;lv_draw_arc_dsc_init(&d);d.width=width;d.color=lv_color_hex(track);
    lv_draw_arc(s_draw,&d,&center,size/2,0,360);
    if(value>0) { d.color=lv_color_hex(ink);d.rounded=1;
        lv_draw_arc(s_draw,&d,&center,size/2,270,270+(clamp(value)*360+50)/100); }
}
static const char* name(const Session& s) { return s.available?s.name:"--"; }
static const char* volume(const Session& s,bool percent=false) {
    return s.available?fmt(percent?"%u%%":"%u",s.volume):"--";
}
static const char* role(const Session& s,bool focused=false) {
    if(!s.available)return "NO SESSION";
    if(s.muted&&s.isDefault)return focused?"FOCUS / DEFAULT / MUTE":"DEFAULT / MUTED";
    if(s.muted)return focused?"FOCUSED / MUTED":"MUTED";
    if(s.isDefault)return focused?"FOCUSED / DEFAULT":"WINDOWS DEFAULT";
    return focused?"FOCUSED":"AVAILABLE";
}
static const char* currentRole() {
    if(!m.current.available)return "WAITING FOR SESSION";
    if(m.current.muted)return m.current.isDefault?"DEFAULT / MUTED":"MUTED / STORED LEVEL";
    return m.mode==3?"APPLICATION VOLUME":m.current.isDefault?"DEFAULT DEVICE":"DEVICE VOLUME";
}
static const char* modeName() {
    return m.mode==2?"INPUT":m.mode==3?"APPLICATION":m.mode==4?"GAME MIXER":m.mode==5?"PC HEALTH":"OUTPUT";
}
static const char* selectTitle() {
    return m.mode==4?(m.selectChannel=='B'?"SELECT CHANNEL B":"SELECT CHANNEL A"):
           m.mode==3?"APPLICATION / BROWSE":m.mode==2?"INPUT / BROWSE":"OUTPUT / BROWSE";
}
static const char* mediaTitle() {
    if(!m.mediaValid||!m.mediaTitle[0])return "No media information";
    if(m.mediaArtist[0])std::snprintf(s_mediaText,sizeof s_mediaText,"%s - %s",m.mediaArtist,m.mediaTitle);
    else std::snprintf(s_mediaText,sizeof s_mediaText,"%s",m.mediaTitle);
    return s_mediaText;
}
static const char* mediaStatus() { return !m.mediaValid?"PC / NO MEDIA":m.mediaPlaying?"PC / GLOBAL / PLAYING":"PC / GLOBAL / PAUSED"; }
static const char* stats(unsigned value,bool percent=true) { return m.statsValid?fmt(percent?"%u%%":"%u",value):"--"; }
static const char* temp(unsigned value) { return m.statsValid&&value?fmt("%u C",value):"-- C"; }
static const char* ramInfo() {
    static char b[32];if(!m.statsValid)return "-- / -- GB";
    std::snprintf(b,sizeof b,"%.1f / %.1f GB",m.ramUsedMB/1024.0,m.ramTotalMB/1024.0);return b;
}
static const char* net(bool up) { return m.statsValid?decimal(up?m.netUpKBps:m.netDownKBps," MB/s"):"-- MB/s"; }
static const char* netBoth() {
    static char b[64];if(!m.statsValid)return "DOWN -- / UP -- MB/s";
    std::snprintf(b,sizeof b,"DOWN %.1f / UP %.1f MB/s",m.netDownKBps/1024.0,m.netUpKBps/1024.0);return b;
}
static const char* debugInfo() {
    static char b[64];std::snprintf(b,sizeof b,"%s %lums H%luK RX%lu",m.pcConnected?"L":"OFF",
        (unsigned long)m.serialAgeMs,(unsigned long)(m.freeHeap/1024),(unsigned long)m.rxFrames);return b;
}
static const Session& slot(int i) { return i==0?m.previous:i==1?m.current:m.next; }
} // namespace v

#include "themes/WindowsDark.inc"
#include "themes/Studio.inc"
#include "themes/Paper.inc"
#include "themes/Orbit.inc"
#include "themes/Pixel.inc"
#include "themes/Blocks.inc"
#include "themes/Terminal.inc"

static void Draw(lv_event_t* event) {
    if(lv_event_get_code(event)==LV_EVENT_DELETE) { if(lv_event_get_target(event)==s_root)s_root=nullptr;return; }
    if(lv_event_get_code(event)!=LV_EVENT_DRAW_MAIN)return;
    s_draw=lv_event_get_draw_ctx(event);lv_obj_get_coords(lv_event_get_target(event),&s_origin);
    switch(s_theme) {
        case 1: windowsdark::draw(s_root);break;
        case 2: studio::draw(s_root);break;
        case 3: paper::draw(s_root);break;
        case 4: orbit::draw(s_root);break;
        case 5: pixel::draw(s_root);break;
        case 6: blocks::draw(s_root);break;
        case 7: terminal::draw(s_root);break;
        default:break;
    }
    s_draw=nullptr;
}

bool Render(uint8_t themeId,const ViewModel& view) {
    if(themeId<1||themeId>7)return false;
    bool changed=themeId!=s_theme||std::memcmp(&m,&view,sizeof m)!=0;
    bool newText=!s_root||themeId!=s_theme||view.page!=m.page||view.mode!=m.mode||
        view.current.isDefault!=m.current.isDefault||view.mediaValid!=m.mediaValid||
        std::strcmp(view.current.name,m.current.name)!=0||
        std::strcmp(view.mediaTitle,m.mediaTitle)!=0||std::strcmp(view.mediaArtist,m.mediaArtist)!=0;
    if(newText){s_scrollCount=0;s_scrollStarted=lv_tick_get();s_scrollUpdated=s_scrollStarted;}
    s_theme=themeId;std::memcpy(&m,&view,sizeof m);
    if(!s_root) {
        s_root=lv_obj_create(lv_scr_act());if(!s_root)return false;
        lv_obj_remove_style_all(s_root);lv_obj_set_pos(s_root,0,0);lv_obj_set_size(s_root,320,240);
        lv_obj_clear_flag(s_root,LV_OBJ_FLAG_SCROLLABLE|LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_event_cb(s_root,Draw,LV_EVENT_ALL,nullptr);changed=true;
    }
    if(changed)lv_obj_invalidate(s_root);
    return true;
}
void Destroy() {
    if(s_root) { auto* old=s_root;s_root=nullptr;lv_obj_del(old); }
    s_scrollCount=0;
}
bool Exists() { return s_root!=nullptr; }
void Tick() {
    uint32_t now=lv_tick_get();
    if(!s_root||!s_scrollCount||uint32_t(now-s_scrollUpdated)<40U)return;
    s_scrollUpdated=now;
    for(uint8_t i=0;i<s_scrollCount;i++)lv_obj_invalidate_area(s_root,&s_scrollAreas[i]);
}
} // namespace ThemeUI
