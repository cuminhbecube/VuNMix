// Small LVGL double for executing the firmware clock's ownership/update logic.
// This checks object reuse and bounds, not LVGL rasterization or native heap use.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <string>
#include <vector>
using lv_coord_t = int16_t;
using lv_color_t = uint32_t;
struct lv_font_t { int line_height; };
constexpr lv_font_t lv_font_dseg_90_bpp1{90}, lv_font_montserrat_10{10},
    lv_font_montserrat_12{12}, lv_font_montserrat_14{14}, lv_font_montserrat_16{16},
    lv_font_montserrat_20{20}, lv_font_montserrat_36{36};
enum lv_align_t { LV_ALIGN_CENTER, LV_ALIGN_TOP_MID, LV_ALIGN_BOTTOM_MID,
    LV_ALIGN_TOP_LEFT, LV_ALIGN_LEFT_MID, LV_ALIGN_BOTTOM_LEFT, LV_ALIGN_TOP_RIGHT };
enum { LV_PART_MAIN, LV_PART_INDICATOR, LV_PART_KNOB, LV_OPA_TRANSP = 0,
    LV_OPA_COVER = 255, LV_RADIUS_CIRCLE = 32767, LV_OBJ_FLAG_SCROLLABLE = 1,
    LV_OBJ_FLAG_CLICKABLE = 2, LV_OBJ_FLAG_HIDDEN = 4 };
struct lv_event_t;
struct lv_obj_t {
    void (*draw)(lv_event_t*) = nullptr;
    lv_obj_t* parent = nullptr;
    int w = 0, h = 0, x = 0, y = 0, flags = 0, value = 0;
    uint32_t bg = 0;
    std::string text;
};
struct lv_meter_scale_t {};
struct lv_meter_indicator_t { int value = 0; };
static lv_obj_t root;
static std::vector<std::unique_ptr<lv_obj_t>> objects;
static int allocations = 0;
static lv_obj_t* lv_scr_act() { root.w = 320; root.h = 240; return &root; }
static lv_obj_t* lv_obj_create(lv_obj_t* parent) {
    objects.emplace_back(new lv_obj_t{});
    auto* obj = objects.back().get(); obj->parent = parent; ++allocations; return obj;
}
static lv_obj_t* lv_label_create(lv_obj_t* p) { return lv_obj_create(p); }
static lv_obj_t* lv_arc_create(lv_obj_t* p) { return lv_obj_create(p); }
static lv_obj_t* lv_meter_create(lv_obj_t* p) { return lv_obj_create(p); }
static uint32_t lv_color_hex(uint32_t c) { return c; }
static void lv_obj_set_size(lv_obj_t* o, int w, int h) { o->w = w; o->h = h; }
static void lv_obj_set_pos(lv_obj_t* o, int x, int y) { o->x = x; o->y = y; }
static void lv_obj_align(lv_obj_t* o, lv_align_t align, int x, int y) {
    auto* p = o->parent; assert(p);
    switch (align) {
      case LV_ALIGN_CENTER: o->x=(p->w-o->w)/2+x; o->y=(p->h-o->h)/2+y; break;
      case LV_ALIGN_TOP_MID: o->x=(p->w-o->w)/2+x; o->y=y; break;
      case LV_ALIGN_BOTTOM_MID: o->x=(p->w-o->w)/2+x; o->y=p->h-o->h+y; break;
      case LV_ALIGN_TOP_LEFT: o->x=x; o->y=y; break;
      case LV_ALIGN_LEFT_MID: o->x=x; o->y=(p->h-o->h)/2+y; break;
      case LV_ALIGN_BOTTOM_LEFT: o->x=x; o->y=p->h-o->h+y; break;
      case LV_ALIGN_TOP_RIGHT: o->x=p->w-o->w+x; o->y=y; break;
    }
}
static void lv_obj_center(lv_obj_t* o) { lv_obj_align(o, LV_ALIGN_CENTER, 0, 0); }
static void lv_label_set_text(lv_obj_t* o, const char* text) { assert(o); o->text=text; }
static void lv_obj_set_style_bg_color(lv_obj_t* o, uint32_t c, int) { assert(o); o->bg=c; }
static void lv_obj_clear_flag(lv_obj_t* o, int f) { o->flags &= ~f; }
static void lv_obj_add_flag(lv_obj_t* o, int f) { o->flags |= f; }
static void lv_arc_set_value(lv_obj_t* o, int v) { assert(o); o->value=v; }
#define NOOP(name) template<class... T> static void name(T...) {}
NOOP(lv_obj_set_style_text_font) NOOP(lv_obj_set_style_text_color)
NOOP(lv_obj_set_style_text_letter_space) NOOP(lv_obj_set_style_bg_opa)
NOOP(lv_obj_set_style_border_width) NOOP(lv_obj_set_style_border_color)
NOOP(lv_obj_set_style_pad_all) NOOP(lv_obj_set_style_radius)
NOOP(lv_obj_set_style_arc_width) NOOP(lv_obj_set_style_arc_color)
NOOP(lv_obj_remove_style) NOOP(lv_arc_set_bg_angles) NOOP(lv_arc_set_range)
NOOP(lv_arc_set_rotation) NOOP(lv_meter_set_scale_ticks)
NOOP(lv_meter_set_scale_major_ticks) NOOP(lv_meter_set_scale_range)
#undef NOOP
static lv_meter_scale_t scale;
static lv_meter_indicator_t indicators[3];
static int indicator_index = 0;
static lv_meter_scale_t* lv_meter_add_scale(lv_obj_t*) { indicator_index=0; return &scale; }
static lv_meter_indicator_t* lv_meter_add_needle_line(lv_obj_t*, lv_meter_scale_t*, int, uint32_t, int) {
    return &indicators[indicator_index++];
}
static void lv_meter_set_indicator_value(lv_obj_t*, lv_meter_indicator_t* i, int v) { i->value=v; }
constexpr int SW=320, SH=240;
constexpr uint32_t COL_BG=0x141218, COL_CYAN=0x06B6D4, COL_ON_SURFACE_V=0xCBC4D2;
constexpr uint8_t CLOCK_STYLE_COUNT=16;
struct Settings { uint8_t clockStyle=0; } g_Settings;
static uint8_t GetClockStyle(const Settings& settings) { return settings.clockStyle; }
enum class ScreenType { NONE, CLOCK };
static ScreenType s_currentScreen=ScreenType::NONE;

struct lv_draw_ctx_t {};
struct lv_area_t { lv_coord_t x1,y1,x2,y2; };
struct lv_point_t { lv_coord_t x,y; };
struct lv_event_t { lv_obj_t* target; };
constexpr int LV_EVENT_DRAW_MAIN=1, LV_TEXT_ALIGN_CENTER=0;
struct lv_draw_rect_dsc_t { uint32_t bg_color; int bg_opa,radius; };
struct lv_draw_label_dsc_t { const lv_font_t* font; uint32_t color; int align; };
struct lv_draw_line_dsc_t { uint32_t color; int width; };
static void lv_draw_rect_dsc_init(lv_draw_rect_dsc_t* d) { *d={}; }
static void lv_draw_label_dsc_init(lv_draw_label_dsc_t* d) { *d={}; }
static void lv_draw_line_dsc_init(lv_draw_line_dsc_t* d) { *d={}; }
static int lv_event_get_code(lv_event_t*) { return LV_EVENT_DRAW_MAIN; }
static lv_obj_t* lv_event_get_target(lv_event_t* e) { return e->target; }
static lv_draw_ctx_t* lv_event_get_draw_ctx(lv_event_t*) { static lv_draw_ctx_t ctx; return &ctx; }
static void lv_obj_get_coords(lv_obj_t* o, lv_area_t* area) {
    *area={lv_coord_t(o->x),lv_coord_t(o->y),lv_coord_t(o->x+o->w-1),lv_coord_t(o->y+o->h-1)};
}
static void lv_obj_add_event_cb(lv_obj_t* o, void (*cb)(lv_event_t*), int, void*) { o->draw=cb; }
static void lv_obj_invalidate(lv_obj_t* o) { if(o->draw) { lv_event_t e{o}; o->draw(&e); } }
static void CheckDrawBounds(const lv_area_t* a) {
    assert(a->x1>=16 && a->x2<304 && a->y1>=42 && a->y2<198);
}
static void lv_draw_rect(lv_draw_ctx_t*, const lv_draw_rect_dsc_t*, const lv_area_t* a) { CheckDrawBounds(a); }
static void lv_draw_label(lv_draw_ctx_t*, const lv_draw_label_dsc_t*, const lv_area_t* a, const char*, void*) { CheckDrawBounds(a); }
static void lv_draw_line(lv_draw_ctx_t*,const lv_draw_line_dsc_t*,const lv_point_t* a,const lv_point_t* b) {
    assert(a->x>=16 && a->x<304 && b->x>=16 && b->x<304);
    assert(a->y>=42 && a->y<198 && b->y>=42 && b->y<198);
}
