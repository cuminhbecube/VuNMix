# VuNMix

VuNMix là bộ điều khiển âm lượng PC dùng ESP32-S3, màn hình màu ST7789, bàn phím ma trận 2x3 và cảm ứng CST816S. Thiết bị giao tiếp với ứng dụng VuNMix Desktop trên Windows qua USB-CDC để điều khiển âm lượng đầu ra, đầu vào, từng ứng dụng và chế độ trộn Game/Voice.

Dự án lấy cảm hứng từ ý tưởng MaxMix, nhưng firmware ESP32-S3, giao thức truyền, giao diện LVGL và ứng dụng desktop Python đã được viết lại để phù hợp với phần cứng VuNMix.

## Tính năng chính

- Điều khiển âm lượng Windows trực tiếp từ thiết bị phần cứng.
- 5 chế độ hiển thị: Output, Input, Application, Game Mixer và Device Health.
- Chọn nhanh thiết bị đầu ra hoặc đầu vào mặc định của Windows.
- Điều chỉnh âm lượng từng ứng dụng đang phát âm thanh.
- Chế độ Game Mixer có 2 kênh A/B để cân bằng Game và Voice chat.
- VU Meter thời gian thực cho Output, Input, Application và Game Mixer.
- VU Meter Input dùng capture stream riêng nên vẫn đo được mức microphone thực tế.
- Device Health / Debug screen hiển thị kết nối, RAM, serial, lỗi CRC/protocol và trạng thái touch.
- Cảm ứng CST816S: vuốt, chạm, chạm hai lần và nhấn giữ.
- Tên thiết bị Input/Output dài tự chạy chữ khi đang ở màn hình thiết bị mặc định.
- Giao diện Cyber-Tactile bằng LVGL 8.3, màu riêng theo từng chế độ.
- LED NeoPixel hiển thị trạng thái, hiệu ứng standby và sleep mode.
- Ứng dụng desktop có system tray, settings popup, auto reconnect và firmware updater.
- Có thể cập nhật firmware `.bin` từ app desktop mà không cần mở PlatformIO.

## Kiến trúc tổng quan

```text
Windows Audio APIs
        ^
        |
VuNMix Desktop App (Python)
        ^
        | USB-CDC framed protocol + CRC
        v
ESP32-S3 Firmware
        |
        +-- ST7789 TFT / LVGL UI
        +-- CST816S touch
        +-- Matrix keypad
        +-- NeoPixel LEDs
```

### Firmware ESP32-S3

Firmware nằm trong thư mục `src/` và được build bằng PlatformIO.

- `main.cpp`: vòng lặp chính, xử lý mode, input, sleep, cập nhật display và LED.
- `Communications.cpp`: giao thức USB-CDC, frame, CRC, queue gửi lệnh.
- `Display.cpp`: toàn bộ UI LVGL, màn hình mode, VU meter, marquee text.
- `Input.cpp`: bàn phím ma trận và cảm ứng CST816S.
- `Config.h`: phiên bản firmware, chân GPIO, thông số phần cứng.
- `Enums.h`, `Structs.h`: command, mode và cấu trúc dữ liệu chia sẻ với desktop.

### VuNMix Desktop

Ứng dụng desktop nằm trong thư mục `desktop/`.

- `vunmix.py`: entry point.
- `app_controller.py`: điều phối serial, audio service, meter, reconnect và firmware update.
- `audio_service.py`: lấy danh sách output/input/app session, đổi default device, chỉnh volume.
- `audio_capture.py`: đo peak microphone bằng `sounddevice`.
- `serial_service.py`: đọc/ghi USB serial.
- `protocol.py`: frame protocol, struct pack/unpack tương ứng firmware.
- `gui.py`: giao diện settings và firmware update.
- `firmware_updater.py`: kiểm tra và nạp firmware ESP32-S3 application image.

## Chế độ sử dụng

### 1. Output

Dùng để quản lý thiết bị phát âm thanh như loa, tai nghe, HDMI audio hoặc USB DAC.

- Ở màn hình chọn, bạn có thể chuyển qua lại giữa các output device.
- Khi chọn một thiết bị không phải default, thao tác vào edit sẽ gửi yêu cầu đặt thiết bị đó làm default của Windows.
- Khi đang edit, tăng/giảm sẽ thay đổi âm lượng output hiện tại.
- VU Meter hiển thị mức âm thanh đang phát trên output được chọn.

### 2. Input

Dùng để quản lý microphone hoặc thiết bị thu âm.

- Hiển thị danh sách input device Windows nhận được.
- Có thể chọn microphone làm default input.
- Khi edit, tăng/giảm sẽ chỉnh mức volume/gain của microphone.
- VU Meter Input lấy peak PCM thực tế từ microphone, không phụ thuộc việc có app ghi âm đang mở hay không.

### 3. Application

Dùng để chỉnh âm lượng từng ứng dụng.

- Chỉ các ứng dụng có audio session đang hoạt động mới xuất hiện.
- Có thể chỉnh riêng Chrome, Spotify, game, Discord, Zalo... mà không đổi master volume.
- Nếu ứng dụng chưa phát âm thanh, Windows có thể chưa tạo session nên app chưa hiện trong danh sách.
- Có thể chọn App Favorites trong VuNMix Desktop Settings. Các app favorite sẽ được ưu tiên hiện trước trong Application/Game mode.
- Desktop gửi icon 16x16 của app xuống thiết bị; nếu không trích xuất được icon thật, app sẽ dùng icon fallback theo chữ cái/màu riêng để vẫn dễ nhận diện.

### 4. Game Mixer

Dùng để cân bằng hai nguồn âm thanh, ví dụ Game và Discord.

- Kênh A thường dùng cho game.
- Kênh B thường dùng cho voice chat.
- Thiết bị hiển thị 2 thanh volume và 2 meter độc lập.
- Có thể chọn kênh A/B rồi chỉnh âm lượng từng bên.

## Điều khiển bằng phím

Thiết bị dùng keypad 2 hàng x 3 cột. Mapping mặc định:

| Phím | Ký tự nội bộ | Chức năng |
| :--- | :---: | :--- |
| Mute | `P` | Mute/unmute kênh hoặc thiết bị hiện tại |
| Navigate/Edit | `M` | Chuyển giữa màn hình chọn và màn hình chỉnh |
| Next Mode | `N` | Chuyển vòng Output -> Input -> Application -> Game |
| Vol - | `-` | Edit: giảm volume; Navigate: chọn mục trước |
| Vol + | `+` | Edit: tăng volume; Navigate: chọn mục sau |
| Play/Pause | khoảng trắng | Dự phòng cho điều khiển media |

Khi giữ `Vol -` hoặc `Vol +`, firmware tạo bước lặp liên tục để cuộn hoặc chỉnh âm lượng nhanh hơn.

## Điều khiển cảm ứng CST816S

| Thao tác | Chức năng |
| :--- | :--- |
| Vuốt trái/phải | Chọn thiết bị hoặc ứng dụng trước/sau |
| Vuốt lên/xuống | Tăng/giảm volume theo bước 5% |
| Chạm một lần | Chuyển Navigate/Edit |
| Chạm hai lần | Mute/unmute |
| Nhấn giữ khoảng 1 giây | Chuyển mode |
| Thao tác khi màn hình ngủ | Chỉ đánh thức màn hình, không thực hiện lệnh |

Cảm ứng và keypad hoạt động song song. Nếu cảm ứng bị đảo hướng trên biến thể màn hình khác, kiểm tra `TOUCH_ROTATION` trong `src/Config.h`.

### Test phím và cảm ứng khi chưa kết nối PC

Khi thiết bị đang ở màn hình chờ kết nối PC, có thể test trực tiếp phần cứng mà không cần mở VuNMix Desktop:

- Nhấn bất kỳ phím vật lý nào để vào màn `INPUT TEST`.
- Hoặc chạm/vuốt màn hình cảm ứng để vào cùng màn test này.
- 6 ô `P`, `M`, `N`, `-`, `SPC`, `+` sẽ sáng khi phím tương ứng được nhấn.
- Dòng `TOUCH READY`/`TOUCH NOT FOUND` cho biết firmware có nhận được CST816S qua I2C hay không.
- Dòng `LAST: ...` hiển thị thao tác cảm ứng cuối cùng như `TAP`, `DOUBLE TAP`, `LONG PRESS`, `SWIPE LEFT/RIGHT/UP/DOWN`.
- Dòng raw `RAW/F/X/Y/INT` dùng để debug sâu hơn: raw gesture, số ngón, tọa độ và trạng thái chân INT. Firmware vẫn poll touch định kỳ nên vẫn test được cả khi chân INT không hoạt động đúng.

## VU Meter

VuNMix Desktop đọc peak audio khoảng 15 lần/giây và gửi về firmware bằng command `METER_LEVEL`.

- Output: đọc peak từ endpoint render của Windows.
- Input: mở capture stream nhẹ bằng `sounddevice` để lấy peak microphone thật.
- Application: đọc peak từ audio session của ứng dụng.
- Game: gửi 2 giá trị meter cho kênh A và B.

Meter chỉ dùng để hiển thị. Nó không thay đổi volume đã đặt.

## Marquee tên dài

Ở màn hình chỉnh của Input/Output, nếu mục đang chọn là thiết bị default và tên quá dài, label sẽ tự chạy chữ để đọc được đầy đủ tên thiết bị. Chức năng này không áp dụng cho màn hình chọn nhanh hoặc danh sách app để tránh gây rối khi chuyển mục liên tục.

## Sleep, clock standby và LED

VuNMix có cơ chế tiết kiệm điện và hiệu ứng chờ:

- Tự tắt backlight TFT sau thời gian không thao tác.
- NeoPixel chuyển sang hiệu ứng standby khi màn hình ngủ.
- Có nhiều hiệu ứng LED chờ, chọn trong VuNMix Desktop Settings.
- Có thể bật/tắt Auto Sleep.
- Có thể cấu hình Clock Standby để hiển thị đồng hồ khi không có hoạt động âm thanh trong một khoảng thời gian.
- Khi PC sleep, desktop app gửi lệnh để thiết bị chuyển trạng thái nghỉ; khi PC resume, app đẩy lại state để đồng bộ.

## Phần cứng yêu cầu

- ESP32-S3 DevKitC-1 N16R8 hoặc board ESP32-S3 tương đương có native USB.
- Màn hình ST7789 TFT 2.4 inch, 320x240, SPI.
- IC cảm ứng CST816S, giao tiếp I2C.
- Bàn phím ma trận 2x3.
- NeoPixel/WS2812 RGB LED, cấu hình hiện tại dùng 10 LED.
- Cáp USB data tốt, cắm vào cổng native USB của ESP32-S3.

## Pinout

### ST7789 TFT

| TFT | ESP32-S3 | Ghi chú |
| :--- | :---: | :--- |
| MOSI/SDA | GPIO 17 | SPI MOSI |
| SCK/SCL | GPIO 16 | SPI clock |
| DC/RS | GPIO 15 | Data/command |
| RST/RES | GPIO 18 | Reset display |
| CS | GND | Luôn chọn màn hình |
| BLK | GPIO 8 | Điều khiển backlight |

### CST816S Touch

| Touch | ESP32-S3 | Ghi chú |
| :--- | :---: | :--- |
| SDA | GPIO 5 | I2C data |
| SCL | GPIO 4 | I2C clock |
| INT | GPIO 6 | Interrupt |
| RST | GPIO 7 | Reset touch |

### Keypad 2x3

| Keypad | ESP32-S3 |
| :--- | :---: |
| Row 0 | GPIO 38 |
| Row 1 | GPIO 41 |
| Col 0 | GPIO 42 |
| Col 1 | GPIO 40 |
| Col 2 | GPIO 39 |

### NeoPixel và nút boot

| Thành phần | ESP32-S3 | Ghi chú |
| :--- | :---: | :--- |
| NeoPixel data | GPIO 45 | `PIXELS_COUNT = 10` |
| BOOT | GPIO 9 | Nút boot trên board |

## Build firmware bằng PlatformIO

### Yêu cầu

- Visual Studio Code.
- Extension PlatformIO IDE.
- Board ESP32-S3 đúng với cấu hình `esp32-s3-devkitc1-n16r8`.

### Build

Mở thư mục project trong VS Code và chạy PlatformIO Build, hoặc dùng terminal:

```powershell
C:\Users\adimi\.platformio\penv\Scripts\pio.exe run
```

### Upload firmware

Cắm ESP32-S3 vào cổng native USB và chạy:

```powershell
C:\Users\adimi\.platformio\penv\Scripts\pio.exe run --target upload --upload-port COM3
```

Thay `COM3` bằng cổng thực tế của thiết bị.

### File firmware sau khi build

Firmware application image nằm tại:

```text
.pio/build/esp32-s3-devkitc1-n16r8/firmware.bin
```

File này có thể được chọn trong VuNMix Desktop để cập nhật firmware.

## Chạy VuNMix Desktop từ source

Yêu cầu Windows và Python 3.11 hoặc 3.12.

```powershell
cd desktop
python -m pip install -r requirements.txt
python vunmix.py
```

Sau khi chạy, app nằm ở system tray. Settings và log runtime được lưu ở:

```text
%LOCALAPPDATA%\VuNMix
```

Log thường dùng để kiểm tra lỗi:

```text
%LOCALAPPDATA%\VuNMix\vunmix.log
```

## Build bản desktop release

Từ thư mục `desktop/`, có thể build bằng PyInstaller:

```powershell
cd desktop
python -m pip install -r requirements.txt
python -m PyInstaller --clean --noconfirm VuNMix.spec --distpath dist_release --workpath build_release
```

File chạy sau build:

```text
desktop/dist_release/VuNMix/VuNMix.exe
```

Script Inno Setup nằm ở:

```text
desktop/VuNMix_Installer.iss
```

## Cập nhật firmware từ Desktop App

1. Chạy `VuNMix.exe` hoặc `python vunmix.py`.
2. Đảm bảo thiết bị đang connected.
3. Mở Settings từ system tray.
4. Ở mục Device Firmware, chọn `Update .bin`.
5. Chọn file `.pio/build/esp32-s3-devkitc1-n16r8/firmware.bin`.
6. Chờ quá trình ghi hoàn tất và thiết bị tự reconnect.

Updater chỉ ghi application partition ở địa chỉ `0x10000`. Bootloader, partition table, NVS và OTA slot còn lại được giữ nguyên. Không rút cáp trong lúc cập nhật.

## Giao thức USB-CDC

Firmware và desktop dùng frame nhị phân có marker và CRC để tránh lỗi do byte rác khi boot hoặc mất đồng bộ serial.

Các nhóm dữ liệu chính:

- `TEST`: handshake và đọc version firmware.
- `SETTINGS`: cấu hình sleep, LED, clock standby.
- `SESSION_INFO`: mode hiện tại, index đang chọn, số lượng session.
- `CURRENT_SESSION`, `ALTERNATE_SESSION`, `PREVIOUS_SESSION`, `NEXT_SESSION`: thông tin các mục quanh vị trí hiện tại.
- `VOLUME_*_CHANGE`: thay đổi volume/mute/default.
- `MODE_STATES`: trạng thái Navigate/Edit của từng mode.
- `TIME_SYNC`: đồng bộ giờ cho clock standby.
- `METER_LEVEL`: VU meter hiện tại.
- `APP_ICON_META`, `APP_ICON_CHUNK`: đẩy icon app 16x16 RGB565 lên thiết bị.
- `SLEEP`: PC sleep hoặc app yêu cầu thiết bị nghỉ.

Desktop và firmware phải giữ `Enums.h`, `Structs.h` và `desktop/protocol.py` đồng bộ. Khi thêm command hoặc đổi struct, cần cập nhật cả hai phía và test protocol. `MODE_STATES` hiện có 6 byte vì có thêm `MODE_HEALTH`.

## Device Health / Debug screen

Firmware có thêm mode `HEALTH` để xem nhanh tình trạng thiết bị ngay trên màn hình. Từ các mode chính, nhấn giữ encoder hoặc long-press cảm ứng để chuyển qua các mode cho tới icon bánh răng.

Màn hình Health hiển thị:

- `CONN`: trạng thái PC/serial và thời gian từ frame gần nhất.
- `UPTIME`: thời gian firmware đã chạy.
- `HEAP` / `ALLOC`: RAM trống, RAM thấp nhất và block cấp phát lớn nhất.
- `SERIAL`: số frame RX/TX.
- `ERR`: số lỗi CRC/protocol và command gần nhất.
- `STATE`: mode/index và số Output/Input/App session.
- `TOUCH`: trạng thái CST816S và số sample touch đã đọc.

Trong Health mode, xoay encoder hoặc swipe không thay đổi session/volume. Nhấn giữ để chuyển sang mode tiếp theo.

## Cấu hình người dùng

Desktop lưu cấu hình tại `%LOCALAPPDATA%\VuNMix`, không ghi trực tiếp vào thư mục cài đặt. Điều này giúp bản cài trong `Program Files` vẫn chạy bình thường mà không cần quyền administrator.

Các thiết lập chính:

- COM port hoặc auto detect.
- App Favorites.
- Sleep timeout.
- Auto Sleep.
- Standby LED effect.
- Clock Standby minutes.
- Update interval.

## Kiểm thử

Chạy unit test desktop:

```powershell
python -m unittest discover -s desktop/tests -v
```

Các nhóm test hiện có:

- Protocol frame, CRC, parser và struct pack/unpack.
- Serial service.
- App controller selection/default logic.
- Audio service helper.
- Firmware updater validation.

## Xử lý lỗi thường gặp

### App báo connected nhưng thiết bị vẫn waiting

- Kiểm tra đã cắm đúng cổng native USB của ESP32-S3 chưa.
- Đóng app rồi mở lại để serial reconnect.
- Kiểm tra log tại `%LOCALAPPDATA%\VuNMix\vunmix.log`.
- Nếu vừa flash firmware, chờ ESP32-S3 reset xong rồi reconnect.
- Đảm bảo desktop và firmware dùng cùng protocol version/struct.

### Tất cả giá trị volume hoặc meter đều là 0

- Kiểm tra thiết bị audio Windows có đang phát/thu thật không.
- Với Input, chọn đúng microphone trong Windows và cấp quyền microphone cho desktop nếu Windows yêu cầu.
- Một số app chỉ xuất hiện khi đang phát âm thanh.
- Thử đổi sang Output/Input default rồi quay lại.
- Kiểm tra `sounddevice` đã cài đúng nếu chạy từ source.

### Không chọn được đầu ra hoặc đầu vào âm thanh

- Ở Output/Input, chuyển tới thiết bị cần chọn rồi vào Edit. Firmware sẽ đánh dấu thiết bị đó là default và desktop sẽ gọi Windows API để đổi default device.
- Nếu Windows chặn đổi default, thử chạy app lại hoặc kiểm tra quyền hệ thống/audio driver.
- Nếu có nhiều thiết bị trùng tên, xem log để biết endpoint nào đang được chọn.

### Input VU Meter không nhảy

- Kiểm tra microphone có tín hiệu thật không.
- Kiểm tra Windows Privacy > Microphone.
- Thử chọn đúng input device trong VuNMix.
- Nếu dùng USB mic, thử rút cắm lại để PortAudio/WASAPI cập nhật danh sách.

### Màn hình cảm ứng bị ngược hướng

Mở `src/Config.h` và thử đổi:

```cpp
static const uint8_t TOUCH_ROTATION = 1;
```

sang giá trị khác phù hợp với module màn hình.

### Upload firmware không thấy cổng COM

- Dùng cáp USB data, không dùng cáp chỉ sạc.
- Giữ BOOT rồi nhấn RESET nếu board không tự vào bootloader.
- Kiểm tra Device Manager của Windows.
- Dùng `--upload-port COMx` đúng cổng.

### Desktop release thiếu thư viện audio

Nếu build lại app, đảm bảo đã cài dependency trong `requirements.txt`, đặc biệt:

- `pycaw`
- `comtypes`
- `sounddevice`
- `pyserial`
- `esptool`

## Cấu trúc thư mục

```text
VuNMix/
├─ src/                     Firmware ESP32-S3
├─ include/                 Header bổ sung nếu có
├─ lib/                     Thư viện local nếu có
├─ data/                    Asset nhúng vào firmware
├─ desktop/                 Ứng dụng Windows Python
│  ├─ assets/               Icon và tài nguyên desktop
│  ├─ tests/                Unit tests
│  ├─ VuNMix.spec           PyInstaller spec
│  └─ VuNMix_Installer.iss  Inno Setup script
├─ boards/                  Board definition nếu cần
├─ hardware.md              Ghi chú phần cứng
├─ platformio.ini           Cấu hình PlatformIO
└─ README.md
```

## Ghi chú phát triển

- Khi đổi protocol, luôn sửa cả firmware và desktop.
- Khi thêm struct mới, kiểm tra size và thứ tự field ở cả C++ và Python.
- Không gửi meter quá nhanh; hiện desktop gửi khoảng 15Hz để UI mượt mà nhưng không nghẽn USB.
- Các lệnh từ firmware được rate-limit để tránh spam serial khi giữ phím.
- Nên test build firmware, unit test desktop và chạy app thật trước khi đóng gói release.

## English short summary

VuNMix is an ESP32-S3 based PC volume controller with an ST7789 display, CST816S touch input, matrix keypad, NeoPixel LEDs and a Python Windows companion app. It controls Windows output devices, input devices, per-application volume and a dual-channel Game/Voice mixer over a CRC-protected USB-CDC protocol. The project includes live VU meters, touch gestures, sleep/standby effects, desktop settings and firmware update support.

## Credits

- Firmware, hardware integration, LVGL UI and desktop app: VuNL.
- Inspired by the original MaxMix concept by t3knomanzer.
