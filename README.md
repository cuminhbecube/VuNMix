# VuNMix - Cyber-Tactile PC Volume Controller (ESP32-S3)

🌍 *[Read in English](#english-version) | 🇻🇳 [Đọc bằng Tiếng Việt](#phiên-bản-tiếng-việt)*

---

<a id="english-version"></a>
# 🌍 English Version

**VuNMix** is an open-source PC Volume Mixer built and developed based on the original [MaxMix](https://maxmixproject.com/) project. This version features comprehensive hardware and software upgrades, utilizing the **ESP32-S3** microcontroller, a high-resolution ST7789 color TFT display, a 2x3 physical matrix keypad, and a CST816S capacitive touch IC.

The highlight of **VuNMix** is its modern **Cyber-Tactile** graphical user interface, built entirely from scratch using **LVGL 8.3**. The UI delivers a stunning high-tech (Cyberpunk) visual experience with glassmorphism effects, high-contrast neon accents, and buttery-smooth animations.

VuNMix communicates directly with its custom **VuNMix Desktop** app (written in Python) on your PC via the USB-CDC protocol, allowing you to independently adjust app volumes, switch audio devices, and balance Game/Voice chat levels intuitively right on your desk.

---

## 🌟 What's New in the Cyber-Tactile Version?

### 1. User Interface (UI) Upgrades
The UI was completely rebuilt following the **Cyber-Tactile** design philosophy:
- **Persistent UI Shell:** Standardized screen layout with a Header (mode name & status) and a Bottom Navigation Bar. The main content resides in the middle, ensuring flicker-free, seamless tab switching.
- **Glassmorphism Panels:** Display cards and volume faders feature an elegant frosted glass outline effect, adding depth to the UI.
- **Color-coded Modes:** Each mode has a distinct accent color: Cyan (Output), Purple (Input), Green (Application), Orange (Game).
- **RGB Glow Strip:** A glowing neon strip separates the main content and the navigation bar, dynamically changing colors based on the active mode.
- **Large Circular Gauges:** High-resolution circular volume gauges with drop-shadow effects.

### 2. Communication Protocol (Firmware) Upgrades
The USB-CDC connection protocol between the ESP32-S3 and the C# PC software has been re-architected for maximum speed and stability:
- **USB Packet Framing:** Command Bytes and Data Payloads are now combined into a single buffer before transmission over USB-CDC. This completely fixes the "Split Packet Timeout" bug that previously caused the PC to randomly ignore messages.
- **Rate-Limited TX:** A compression algorithm and transmission rate limiter ensure the device only reports its status to the PC at an ultra-fast 33Hz (1 command per 30ms). This prevents data bottlenecks and ensures the PC responds smoothly even during rapid volume adjustments.
- **Anti-Echo Debounce:** Eradicates the "Race Condition" bug that caused volume levels to ping-pong (e.g., jumping from 26 down to 25 and back to 26). When the user interacts with the hardware, the ESP32 temporarily ignores incoming Windows Audio Events for 500ms. This makes VuNMix the "Absolute Truth" controller and eliminates all echo/bounce effects.

---

## 🎛️ Display Modes

VuNMix features 4 primary audio management modes. You can easily identify the active mode via the Bottom Navigation Bar and the accent color.

### 1. 🎧 Output Mode (Cyan)
Manage audio output devices (Speakers, Headphones).
- **Navigate:** Scroll through available output devices.
- **Edit:** Adjust volume, mute, or set the selected device as the Windows Default.

### 2. 🎙️ Input Mode (Purple)
Manage audio input devices (Microphones).
- **Navigate:** View connected microphones.
- **Edit:** Adjust microphone gain/volume or mute.

### 3. 📱 Application Mode (Green)
Displays a list of applications currently playing audio (Spotify, Chrome, Games, Discord...).
- **Navigate:** Select an application to adjust.
- **Edit:** Increase/decrease volume or mute individual apps independently without affecting the master volume or other apps.

### 4. 🎮 Game Mixer Mode (Orange)
An advanced audio mixing mode featuring a **Dual Fader** (two vertical sliders) interface.
Perfect for balancing audio between two specific applications (e.g., balancing your Game audio and Voice chat audio).
- Displays volume levels for Channel **A (GAME)** and Channel **B (VOICE)** side by side.
- A center MIX indicator helps you quickly visualize and balance the audio distribution.

---

## 🕹️ Hardware Controls

The device utilizes a Matrix Keypad combined with software simulation instead of traditional rotary encoders:

### Key Matrix (2x3)
| Key Name | Mapped Char | Detailed Function |
| :--- | :--- | :--- |
| **Prev Tab** | `P` | Double Tap to Mute/Unmute the application or device. |
| **Mute/Set Def**| `M` | Tap to toggle between selecting apps (Navigate) and adjusting volume (Edit). |
| **Next Tab** | `N` | Hold to cycle through modes (Output -> Input -> App -> Game). |
| **Vol -** | `-` | Edit mode: Decrease volume. Navigate mode: Scroll left. Hold for continuous adjustment. |
| **Vol +** | `+` | Edit mode: Increase volume. Navigate mode: Scroll right. Hold for continuous adjustment. |
| **Play/Pause** | ` ` | (Future) Pause/Resume Windows Media playback. |

*(Note: The hardware integrates a CST816S capacitive touch IC. Swipe and touch gestures will be supported in future firmware updates.)*

### NeoPixel LED & Sleep Mode
- **RGB Backlight (NeoPixel):** Displays a breathing effect during sleep mode, a color wave effect on the splash screen, and acts as a dynamic audio level meter colored according to the active app/mode.
- **Power Saving (Sleep Mode):** Automatically turns off the TFT backlight and transitions LED effects if no user input is detected. Press any key to wake the device.

---

## 🛠 Hardware Requirements

1. **Microcontroller:** ESP32-S3 (DevKitC-1 or equivalent).
2. **Display:** ST7789 2.4-inch TFT LCD (SPI interface, 320x240 resolution).
3. **Touch IC:** CST816S (I2C interface).
4. **Keypad:** 2 Columns x 3 Rows Matrix Keypad (6 keys total).
5. **LED:** NeoPixel RGB LED.

### Pinout Configuration

#### 1. TFT Display (ST7789 - SPI)
| TFT Pin | ESP32-S3 Pin | Note |
| :--- | :--- | :--- |
| **MOSI (SDA)** | GPIO 17 | |
| **SCK (SCL)** | GPIO 16 | |
| **DC / RS** | GPIO 15 | |
| **RST / RES** | GPIO 18 | |
| **CS** | GND | Hard-wired to GND (Always On) |
| **BLK** | GPIO 8 | Backlight PWM control |

#### 2. Touch (CST816S - I2C)
| Touch Pin | ESP32-S3 Pin | Note |
| :--- | :--- | :--- |
| **SDA** | GPIO 5 | |
| **SCL** | GPIO 4 | |
| **INT** | GPIO 3 | |
| **RST** | GPIO 2 | |

#### 3. Matrix Keypad (2x3)
| Keypad Pin | ESP32-S3 Pin | Corresponding Keys |
| :--- | :--- | :--- |
| **Row 0** | GPIO 38 | Connects one side of: Prev Tab (Col 0), Mute/Set Def (Col 1), Next Tab (Col 2) |
| **Row 1** | GPIO 41 | Connects one side of: Vol- (Col 0), Play/Pause (Col 1), Vol+ (Col 2) |
| **Col 0** | GPIO 42 | Column 0 Scanner |
| **Col 1** | GPIO 40 | Column 1 Scanner |
| **Col 2** | GPIO 39 | Column 2 Scanner |

#### 4. Misc
| Component | ESP32-S3 Pin | Note |
| :--- | :--- | :--- |
| **NeoPixel (RGB)** | GPIO 45 | Status RGB LED |
| **BOOT Button** | GPIO 9 | Onboard hardware BOOT button |

---

## 💻 Firmware Installation & Build Instructions

This project is built on the Arduino framework and managed using **PlatformIO**.

### 1. Prerequisites:
- [Visual Studio Code](https://code.visualstudio.com/)
- VS Code Extension: [PlatformIO IDE](https://platformio.org/install/ide?install=vscode)

### 2. Build & Upload
1. Clone or download this repository to your computer.
2. Open the project folder in VS Code.
3. PlatformIO will automatically initialize the environment and download required libraries (`TFT_eSPI`, `lvgl 8.3`, `Adafruit NeoPixel`, `Keypad`, etc.).
4. **Connect the ESP32-S3 via USB** (Ensure you plug into the native USB data port, not the UART/CH340 port, as the software relies on native USB-CDC).
5. Click **Build** (✓ icon) in the bottom PlatformIO status bar.
6. Once built successfully, click **Upload** (➔ icon) to flash the firmware onto the ESP32.

---

## 🖥 PC Control Software (VuNMix Desktop App)

VuNMix acts as the display and controller interface. To actually manipulate Windows volume, you need to run the companion background app on your PC. 
While the project's concept was originally inspired by the open-source MaxMix project, the entire system (both the ESP32 firmware and the Windows Desktop application) has been completely rewritten from scratch to support our specific hardware. The new custom desktop software is built using Python and is located in the `desktop/` directory.

1. Open a terminal and navigate to the `desktop/` folder.
2. Install the required Python dependencies: `pip install -r requirements.txt`
3. Run the application: `python vunmix.py`
4. The ESP32-S3 device will automatically be recognized and establish a connection via a Virtual COM port (USB-CDC). The splash screen on the device will disappear, transitioning to the control interface.

---

## 📜 Credits & License

- **UI Design / Hardware / ESP32-S3 Firmware:** Developed and optimized by VuN.
- **Inspiration:** Inspired by the concept and protocol idea of the [MaxMix Project](https://maxmixproject.com) by [t3knomanzer](https://github.com/t3knomanzer).

<br><br><br>

---
---

<a id="phiên-bản-tiếng-việt"></a>
# 🇻🇳 Phiên bản Tiếng Việt

**VuNMix** là dự án bộ điều khiển âm lượng PC (PC Volume Mixer) mã nguồn mở, được xây dựng và phát triển dựa trên dự án gốc [MaxMix](https://maxmixproject.com/). Phiên bản VuNMix được nâng cấp toàn diện về mặt phần cứng và phần mềm, sử dụng vi điều khiển **ESP32-S3**, kết hợp cùng màn hình màu TFT ST7789 độ phân giải cao, bàn phím ma trận vật lý 2x3 và IC cảm ứng điện dung CST816S.

Điểm nhấn của **VuNMix** là giao diện đồ hoạ **Cyber-Tactile** hiện đại được thiết kế hoàn toàn mới bằng thư viện **LVGL 8.3**. Giao diện mang lại trải nghiệm thị giác High-tech (Cyberpunk) cực kỳ đẹp mắt với hiệu ứng kính mờ (Glassmorphism), màu sắc tương phản cao (Neon accents) và hình ảnh chuyển động mượt mà.

VuNMix giao tiếp trực tiếp với phần mềm **VuNMix Desktop** (được viết bằng Python) trên PC thông qua giao thức USB-CDC, cho phép bạn điều chỉnh âm lượng của từng ứng dụng riêng biệt, chuyển đổi thiết bị âm thanh, và cân bằng âm lượng Game/Voice chat một cách trực quan ngay trên bàn làm việc của bạn.

---

## 🌟 Có gì mới ở phiên bản VuNMix Cyber-Tactile?

### 1. Nâng cấp Giao diện (UI)
Giao diện được đập đi xây lại theo triết lý thiết kế **Cyber-Tactile**:
- **Persistent UI Shell:** Bố cục màn hình được chuẩn hoá với Header (chứa tên chế độ & trạng thái) và Navigation Bar ở dưới cùng. Nội dung chính nằm ở giữa giúp chuyển đổi giữa các tab cực kỳ mượt mà, loại bỏ hoàn toàn hiện tượng nháy màn hình (flicker-free).
- **Glassmorphism Panels:** Các khung hiển thị và thanh trượt (faders) sử dụng hiệu ứng viền kính trong suốt sang trọng, tạo chiều sâu cho giao diện.
- **Color-coded Modes:** Mỗi chế độ hoạt động có một màu nhấn (accent color) đặc trưng: Cyan (Output), Purple (Input), Green (Application), Orange (Game).
- **RGB Glow Strip:** Giao diện có một dải màu Neon sáng rực phân tách vùng nội dung và thanh điều hướng, thay đổi màu sắc tương ứng theo chế độ.
- **Large Circular Gauges:** Thanh hiển thị âm lượng dạng cung tròn lớn với độ phân giải cao và hiệu ứng đổ bóng.

### 2. Nâng cấp Giao thức Giao tiếp (Firmware)
Dự án VuNMix đã tái thiết kế giao thức kết nối USB-CDC giữa ESP32-S3 và phần mềm C# PC để đạt tốc độ và sự ổn định cao nhất:
- **USB Packet Framing:** Toàn bộ Command Byte và Data Payload được gộp chung thành một bộ đệm (buffer) duy nhất trước khi gửi qua USB-CDC. Điều này khắc phục triệt để lỗi "Split Packet Timeout" khiến phần mềm PC thỉnh thoảng bỏ qua tin nhắn.
- **Băng thông mượt mà (Rate-Limited TX):** Thuật toán nén tín hiệu và giới hạn tốc độ gửi (Rate limit) đảm bảo thiết bị chỉ báo cáo trạng thái cho PC với tần số cực nhanh 33Hz (1 lệnh mỗi 30ms). PC sẽ luôn phản hồi mượt mà kể cả khi bạn tăng/giảm âm lượng với tốc độ chóng mặt, loại bỏ hoàn toàn hiện tượng giật lag (Bottleneck) khi truyền dữ liệu.
- **Chống Dội Âm thanh (Anti-Echo Debounce):** Giải quyết triệt để lỗi "Race Condition" khiến mức âm lượng nhảy giật lùi (Ví dụ: vặn lên 26 nhưng nhảy về 25 rồi mới lên 26). Khi người dùng thao tác phần cứng, ESP32 sẽ tạm thời "khóa" không nhận phản hồi ngược từ Windows Audio Event trong vòng 500ms, biến VuNMix thành thiết bị ưu tiên tuyệt đối (Absolute Truth) và loại bỏ hoàn toàn hiện tượng dội lệnh (Ping-Pong Effect).

---

## 🎛️ Các chế độ hoạt động (Display Modes)

VuNMix được chia thành 4 chế độ quản lý âm thanh chính. Bạn có thể dễ dàng nhận biết chế độ đang sử dụng thông qua thanh điều hướng (Bottom Navigation Bar) và màu sắc chủ đạo.

### 1. 🎧 Output Mode (Cyan / Xanh lơ)
Quản lý các thiết bị đầu ra (Loa, Tai nghe). 
- **Navigate:** Cuộn qua danh sách các thiết bị đầu ra khả dụng trên PC.
- **Edit:** Tăng/giảm âm lượng, tắt tiếng (Mute) hoặc đặt thiết bị đang chọn làm thiết bị mặc định của Windows (Set Default).

### 2. 🎙️ Input Mode (Purple / Tím)
Quản lý các thiết bị đầu vào (Microphone). 
- **Navigate:** Xem danh sách microphone đang kết nối.
- **Edit:** Điều chỉnh âm lượng thu âm, hoặc tắt tiếng (Mute) microphone.

### 3. 📱 Application Mode (Green / Xanh lá)
Hiển thị danh sách các phần mềm đang phát âm thanh (Spotify, Chrome, Game, Zalo...).
- **Navigate:** Chọn ứng dụng cần điều chỉnh.
- **Edit:** Tăng/giảm âm lượng hoặc tắt tiếng từng ứng dụng một cách độc lập mà không ảnh hưởng đến âm lượng tổng của máy tính hay các ứng dụng khác.

### 4. 🎮 Game Mixer Mode (Orange / Cam)
Chế độ "Mix" (trộn) âm lượng nâng cao với giao diện **Dual Fader** (2 thanh trượt dọc).
Hỗ trợ cân bằng trực tiếp âm thanh giữa 2 ứng dụng bất kỳ (Ví dụ: Giữa Game bạn đang chơi và ứng dụng Voice chat như Discord).
- Hiển thị song song âm lượng của kênh **A (GAME)** và kênh **B (VOICE)**.
- Thanh chia (MIX) ở giữa giúp bạn dễ dàng so sánh và cân bằng âm thanh hai bên.

---

## 🕹️ Thao tác điều khiển (Hardware Controls)

Thiết bị loại bỏ núm vặn truyền thống và sử dụng Bàn phím Ma trận kết hợp mô phỏng phần mềm:

### Bàn phím ma trận (Key Matrix 2x3)
| Tên Phím | Kí tự Map | Chức năng chi tiết |
| :--- | :--- | :--- |
| **Prev Tab** | `P` | Chạm đúp (Double Tap) để Mute/Unmute ứng dụng. |
| **Mute/Set Def** | `M` | Nhấn (Tap) để chuyển đổi giữa việc chọn ứng dụng (Navigate) và chỉnh volume (Edit). |
| **Next Tab** | `N` | Nhấn giữ (Hold) để chuyển vòng quanh các chế độ (Output -> Input -> App -> Game). |
| **Vol -** | `-` | Ở chế độ Edit: Giảm âm lượng. Ở chế độ Navigate: Cuộn sang trái. Nhấn giữ để cuộn/chỉnh liên tục. |
| **Vol +** | `+` | Ở chế độ Edit: Tăng âm lượng. Ở chế độ Navigate: Cuộn sang phải. Nhấn giữ để cuộn/chỉnh liên tục. |
| **Play/Pause** | ` ` | (Tương lai) Tạm dừng / Tiếp tục Media của Windows. |

*(Ghi chú: Thiết bị phần cứng đã tích hợp sẵn IC cảm ứng điện dung CST816S trên màn hình. Tính năng vuốt chạm sẽ được hỗ trợ trong các bản firmware tương lai.)*

### LED NeoPixel & Chế độ Chờ (Sleep Mode)
- **Đèn nền RGB (NeoPixel):** Chớp tắt nhẹ nhàng (Breathing effect) khi ở trạng thái chờ, hiển thị hiệu ứng sóng màu (Color wave) khi ở Splash Screen, và hoạt động như thanh Audio Level tương ứng với màu sắc của từng ứng dụng/chế độ.
- **Chế độ tiết kiệm điện (Sleep):** Tự động tắt đèn nền màn hình TFT và chuyển hiệu ứng LED nếu không có thao tác nào từ người dùng trong một thời gian cài đặt. Chạm phím bất kỳ để đánh thức màn hình.

---

## 🛠 Phần cứng yêu cầu

1. **Vi điều khiển:** ESP32-S3 (DevKitC-1 hoặc tương đương).
2. **Màn hình:** Màn hình ST7789 2.4 inch TFT LCD giao tiếp SPI (Độ phân giải 320x240).
3. **Cảm ứng:** IC cảm ứng CST816S giao tiếp I2C.
4. **Phím bấm:** Bàn phím ma trận 2 cột x 3 hàng (tổng 6 phím).
5. **LED:** NeoPixel RGB LED.

### Sơ đồ chân kết nối (Pinout)

#### 1. Màn hình TFT (ST7789 - SPI)
| Chân TFT | Chân ESP32-S3 | Ghi chú |
| :--- | :--- | :--- |
| **MOSI (SDA)** | GPIO 17 | |
| **SCK (SCL)** | GPIO 16 | |
| **DC / RS** | GPIO 15 | |
| **RST / RES** | GPIO 18 | |
| **CS** | GND | Nối thẳng xuống mass (Luôn bật) |
| **BLK** | GPIO 8 | Điều khiển tắt/bật đèn nền màn hình |

#### 2. Cảm ứng (CST816S - I2C)
| Chân Touch | Chân ESP32-S3 | Ghi chú |
| :--- | :--- | :--- |
| **SDA** | GPIO 5 | |
| **SCL** | GPIO 4 | |
| **INT** | GPIO 3 | |
| **RST** | GPIO 2 | |

#### 3. Bàn phím ma trận (Key Matrix 2x3)
| Chân Keypad | Chân ESP32-S3 | Phím tương ứng |
| :--- | :--- | :--- |
| **Row 0** | GPIO 38 | Nối chân một bên của nhóm phím: Prev Tab (Col 0), Mute/Set Def (Col 1), Next Tab (Col 2) |
| **Row 1** | GPIO 41 | Nối chân một bên của nhóm phím: Vol- (Col 0), Play/Pause (Col 1), Vol+ (Col 2) |
| **Col 0** | GPIO 42 | Quét cột 0 |
| **Col 1** | GPIO 40 | Quét cột 1 |
| **Col 2** | GPIO 39 | Quét cột 2 |

#### 4. Thành phần khác
| Thành phần | Chân ESP32-S3 | Ghi chú |
| :--- | :--- | :--- |
| **NeoPixel (RGB)** | GPIO 45 | LED RGB hiển thị trạng thái |
| **BOOT Button** | GPIO 9 | Nút Boot cứng trên mạch ESP32 |

---

## 💻 Cài đặt và Biên dịch Firmware

Dự án được xây dựng trên framework Arduino và quản lý thư viện thông qua **PlatformIO**.

### 1. Phần mềm yêu cầu:
- [Visual Studio Code](https://code.visualstudio.com/) (VS Code)
- Extension VS Code: [PlatformIO IDE](https://platformio.org/install/ide?install=vscode)

### 2. Biên dịch & Nạp Firmware (Upload)
1. Tải toàn bộ thư mục mã nguồn dự án này về máy của bạn.
2. Mở thư mục dự án bằng VS Code.
3. PlatformIO sẽ tự động khởi tạo môi trường và tải các thư viện cần thiết (`TFT_eSPI`, `lvgl 8.3`, `Adafruit NeoPixel`, `Keypad`, v.v.).
4. **Cắm cáp USB vào cổng USB của ESP32-S3** (Sử dụng cổng native USB hỗ trợ truyền dữ liệu, không cắm vào cổng UART/CH340 nếu có để tính năng USB-CDC của phần mềm hoạt động).
5. Nhấn **Build** (biểu tượng ✓) ở thanh trạng thái bên dưới cùng màn hình của VS Code.
6. Khi Build hoàn tất không có lỗi, nhấn **Upload** (biểu tượng ➔) để nạp Firmware vào ESP32.

---

## 🖥 Phần mềm điều khiển trên PC (VuNMix Desktop App)

VuNMix chỉ là màn hình hiển thị và bộ điều khiển, để thiết bị có thể thay đổi âm lượng trên Windows, bạn cần chạy ứng dụng nền trên PC.
Mặc dù ý tưởng ban đầu được lấy cảm hứng từ dự án mã nguồn mở MaxMix, toàn bộ hệ thống (từ Firmware ESP32 cho tới phần mềm Desktop) đều đã được viết lại hoàn toàn từ đầu bằng Python để phù hợp và tối ưu hoá cho kiến trúc phần cứng mới. Mã nguồn phần mềm Desktop được lưu trong thư mục `desktop/`.

1. Mở Terminal (hoặc Command Prompt) và trỏ vào thư mục `desktop/`.
2. Cài đặt các thư viện Python cần thiết: `pip install -r requirements.txt`
3. Chạy ứng dụng: `python vunmix.py`
4. Thiết bị ESP32-S3 sẽ tự động được nhận dạng và thiết lập kết nối qua cổng COM ảo (Virtual USB-CDC). Màn hình Splash "VuNMix" trên thiết bị sẽ tự động biến mất và chuyển sang giao diện điều khiển.

---

## 📜 Giấy phép & Tác giả

- **Thiết kế UI / Phần cứng / Firmware ESP32-S3:** Phát triển và tối ưu hoá giao thức bởi VuN.
- **Cảm hứng dự án:** Ý tưởng giao thức và dự án được lấy cảm hứng từ [MaxMix Project](https://maxmixproject.com) của tác giả [t3knomanzer](https://github.com/t3knomanzer).
