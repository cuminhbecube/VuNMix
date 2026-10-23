// Record draw commands emitted by the actual firmware art-clock functions.
// This deliberately contains no Python preview layout or digit/word tables.
#include <cstdint>
#include <cstdio>
using lv_coord_t = int16_t;
struct lv_font_t { int size; int line_height; };
constexpr lv_font_t lv_font_montserrat_12{12, 15},
    lv_font_montserrat_20{20, 22}, lv_font_montserrat_36{36, 40};
struct lv_draw_ctx_t {};
struct lv_area_t { lv_coord_t x1, y1, x2, y2; };
struct lv_point_t { lv_coord_t x, y; };
struct lv_draw_rect_dsc_t { uint32_t bg_color; int bg_opa, radius; };
struct lv_draw_label_dsc_t { const lv_font_t* font; uint32_t color; int align; };
struct lv_draw_line_dsc_t { uint32_t color; int width; };
constexpr int LV_OPA_COVER = 255, LV_TEXT_ALIGN_CENTER = 1;
static uint8_t s_artHour, s_artMinute, s_artSecond;
static uint32_t lv_color_hex(uint32_t value) { return value; }
static void lv_draw_rect_dsc_init(lv_draw_rect_dsc_t* value) { *value = {}; }
static void lv_draw_label_dsc_init(lv_draw_label_dsc_t* value) { *value = {}; }
static void lv_draw_line_dsc_init(lv_draw_line_dsc_t* value) { *value = {}; }
static void lv_draw_rect(lv_draw_ctx_t*, const lv_draw_rect_dsc_t* d, const lv_area_t* a) {
    printf("R\t%d\t%d\t%d\t%d\t%u\t%d\n", a->x1, a->y1,
           a->x2-a->x1+1, a->y2-a->y1+1, unsigned(d->bg_color), d->radius);
}
static void lv_draw_label(lv_draw_ctx_t*, const lv_draw_label_dsc_t* d,
                          const lv_area_t* a, const char* text, void*) {
    printf("T\t%d\t%d\t%d\t%d\t%u\t%s\n", a->x1, a->y1,
           a->x2-a->x1+1, d->font->size, unsigned(d->color), text);
}
static void lv_draw_line(lv_draw_ctx_t*, const lv_draw_line_dsc_t* d,
                         const lv_point_t* a, const lv_point_t* b) {
    printf("L\t%d\t%d\t%d\t%d\t%u\t%d\n", a->x, a->y, b->x, b->y,
           unsigned(d->color), d->width);
}
