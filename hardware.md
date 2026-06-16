# Thông tin phần cứng VuNMix (ESP32-S3)

Dự án VuNMix sử dụng vi điều khiển ESP32-S3 kết hợp với màn hình TFT và cảm ứng điện dung để giao tiếp với PC qua cổng USB (USB-CDC).

## Các thành phần chính
- **Vi điều khiển (MCU):** ESP32-S3 DevKitM-1
- **Màn hình hiển thị:** ST7789 240×320 TFT (Chạy ở chế độ ngang 320×240) giao tiếp qua chuẩn SPI.
- **Cảm ứng:** CST816S (cảm ứng điện dung) giao tiếp qua I2C (địa chỉ 0x15).
- **Phím cứng (Matrix Buttons):** Bàn phím ma trận 2x3 (6 nút bấm).
- **Giao tiếp PC:** USB-CDC Serial

---

## Chi tiết sơ đồ chân kết nối (Pinout)

### 1. Màn hình TFT (ST7789 - SPI)
*Lưu ý: Chân CS được nối cứng xuống GND nên luôn kích hoạt.*
| Chức năng | Chân ESP32-S3 | Ghi chú |
| :--- | :--- | :--- |
| **MOSI (SDA)** | GPIO 17 | Data in |
| **SCK (SCL)** | GPIO 16 | Clock |
| **DC / RS** | GPIO 15 | Data/Command |
| **RST / RES** | GPIO 18 | Reset |
| **CS** | GND | Nối thẳng xuống mass (-1) |
| **Backlight (BLK)** | GPIO 8 | Điều khiển đèn nền màn hình (Mức cao `HIGH` = Bật) |

### 2. Cảm ứng (CST816S - I2C)
| Chức năng | Chân ESP32-S3 | Ghi chú |
| :--- | :--- | :--- |
| **SDA** | GPIO 5 | Dữ liệu I2C |
| **SCL** | GPIO 4 | Xung nhịp I2C |
| **INT** | GPIO 3 | Báo ngắt khi có sự kiện chạm (Active LOW) |
| **RST** | GPIO 2 | Reset IC cảm ứng (Active LOW) |

### 3. Ma trận nút bấm (Key Matrix 2x3)
| Chức năng | Chân ESP32-S3 | Ghi chú |
| :--- | :--- | :--- |
| **Row 0 (Hàng 0)** | GPIO 38 | Đọc tín hiệu nút (Prev Tab, Mute/Set, Next Tab) |
| **Row 1 (Hàng 1)** | GPIO 41 | Đọc tín hiệu nút (Vol Down, Play/Pause, Vol Up) |
| **Col 0 (Cột 0)** | GPIO 42 | Kích hoạt cột |
| **Col 1 (Cột 1)** | GPIO 40 | Kích hoạt cột |
| **Col 2 (Cột 2)** | GPIO 39 | Kích hoạt cột |

**Sơ đồ chức năng các nút:**
- `Row 0, Col 0`: Trở về Tab trước
- `Row 0, Col 1`: Bật/Tắt Mute hoặc Đặt thiết bị làm mặc định (tuỳ Tab)
- `Row 0, Col 2`: Sang Tab tiếp theo
- `Row 1, Col 0`: Giảm âm lượng (Volume Down)
- `Row 1, Col 1`: Phát / Tạm dừng (Play / Pause Media)
- `Row 1, Col 2`: Tăng âm lượng (Volume Up)

### 4. Các kết nối khác
| Chức năng | Chân ESP32-S3 | Ghi chú |
| :--- | :--- | :--- |
| **NeoPixel (LED RGB)**| GPIO 45 | Chân xuất dữ liệu ra LED |
| **BOOT Button** | GPIO 9 | Nút Boot tích hợp trên DevKit (Active LOW) |
