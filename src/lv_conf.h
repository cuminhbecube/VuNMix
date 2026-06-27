/**
 * @file lv_conf.h
 * VuNMix — LVGL v8 configuration
 * ST7789 320×240 landscape, 16-bit colour (RGB565)
 */
#if 1

#ifndef LV_CONF_H
#define LV_CONF_H

#include <stdint.h>

/*====================
   COLOR SETTINGS
 *====================*/
#define LV_COLOR_DEPTH     16    /* RGB565 — matches ST7789 native format */
#define LV_COLOR_16_SWAP    0    /* TFT_eSPI pushColors handles byte order */
#define LV_COLOR_SCREEN_TRANSP 0

/*====================
   MEMORY SETTINGS
 *====================*/
#define LV_MEM_CUSTOM 0
#define LV_MEM_SIZE   (64U * 1024U)   /* 64 KB internal heap */
#define LV_MEM_ADR    0
#define LV_MEM_POOL_INCLUDE <stdlib.h>
#define LV_MEM_POOL_ALLOC   malloc
#define LV_MEM_POOL_FREE    free

/*====================
   HAL SETTINGS
 *====================*/
#define LV_TICK_CUSTOM 1
#define LV_FONT_CUSTOM_DECLARE \
    LV_FONT_DECLARE(lv_font_vn_10) \
    LV_FONT_DECLARE(lv_font_vn_12) \
    LV_FONT_DECLARE(lv_font_vn_14) \
    LV_FONT_DECLARE(lv_font_vn_20)
#define LV_TICK_CUSTOM_INCLUDE  <Arduino.h>
#define LV_TICK_CUSTOM_SYS_TIME_EXPR (millis())

/*====================
   DISPLAY / BUFFER
 *====================*/
#define LV_HOR_RES_MAX 320
#define LV_VER_RES_MAX 240

/*====================
   DRAW
 *====================*/
#define LV_DRAW_COMPLEX 1
#define LV_SHADOW_CACHE_SIZE 0
#define LV_CIRCLE_CACHE_SIZE 4

/*====================
   FONTS
 *====================*/
#define LV_FONT_MONTSERRAT_10 1
#define LV_FONT_MONTSERRAT_12 1
#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_MONTSERRAT_16 1
#define LV_FONT_MONTSERRAT_20 1
#define LV_FONT_MONTSERRAT_24 1
#define LV_FONT_MONTSERRAT_28 1
#define LV_FONT_MONTSERRAT_36 1

#define LV_FONT_DEFAULT &lv_font_montserrat_14

#define LV_FONT_FMT_TXT_LARGE 0
#define LV_USE_FONT_SUBPX     0

/*====================
   WIDGETS
 *====================*/
#define LV_USE_ARC       1
#define LV_USE_BAR       1
#define LV_USE_BTN       1
#define LV_USE_BTNMATRIX 0
#define LV_USE_CANVAS    0
#define LV_USE_CHART     0
#define LV_USE_CHECKBOX  0
#define LV_USE_DROPDOWN  0
#define LV_USE_IMG       1
#define LV_USE_LABEL     1
#define LV_USE_LINE      1
#define LV_USE_LIST      0
#define LV_USE_METER     0
#define LV_USE_MSGBOX    0
#define LV_USE_ROLLER    0
#define LV_USE_SLIDER    1
#define LV_USE_SPINBOX   0
#define LV_USE_SPINNER   0
#define LV_USE_SWITCH    0
#define LV_USE_TABLE     0
#define LV_USE_TABVIEW   0
#define LV_USE_TILEVIEW  0
#define LV_USE_WIN       0
#define LV_USE_TEXTAREA  0

/* Extended widgets — all disabled */
#define LV_USE_ANIMIMG              0
#define LV_USE_CALENDAR             0
#define LV_USE_CALENDAR_HEADER_ARROW    0
#define LV_USE_CALENDAR_HEADER_DROPDOWN 0
#define LV_USE_COLORWHEEL           0
#define LV_USE_IMGBTN               0
#define LV_USE_KEYBOARD             0
#define LV_USE_LED                  0
#define LV_USE_MENU                 0
#define LV_USE_SPAN                 0

/*====================
   THEMES
 *====================*/
#define LV_USE_THEME_DEFAULT 1
  #define LV_THEME_DEFAULT_DARK 1
  #define LV_THEME_DEFAULT_GROW 1
#define LV_USE_THEME_BASIC 0
#define LV_USE_THEME_MONO  0

/*====================
   LAYOUTS
 *====================*/
#define LV_USE_FLEX 1
#define LV_USE_GRID 0

/*====================
   LOGGING / DEBUG
 *====================*/
#define LV_USE_LOG 0
#define LV_USE_ASSERT_NULL          0
#define LV_USE_ASSERT_MALLOC        0
#define LV_USE_ASSERT_STYLE         0
#define LV_USE_ASSERT_MEM_INTEGRITY 0
#define LV_USE_ASSERT_OBJ           0
#define LV_USE_PERF_MONITOR         0
#define LV_USE_MEM_MONITOR          0
#define LV_USE_REFR_DEBUG           0

/*====================
   OTHER
 *====================*/
#define LV_USE_ANIMATION    1
#define LV_ANIM_RESOLUTION  1024

#endif /* LV_CONF_H */
#endif /* Enable content */
