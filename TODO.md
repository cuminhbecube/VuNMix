# Kế hoạch Phát triển & Lộ trình Tính năng Mới (VuNMix TODO Roadmap)

Tài liệu này tổng hợp toàn bộ các tính năng đề xuất nâng cấp cho dự án **VuNMix** (Firmware ESP32-S3 và Desktop Companion App), phân loại theo từng nhóm chức năng và mức độ ưu tiên triển khai.

---

## 🎯 Nhóm 1: Điều khiển Âm thanh & Tích hợp Ứng dụng (Audio & Streaming)

- [x] **1. Tích hợp Media Player (Spotify / Apple Music / Windows SMTC)** ✅ *(Đã hoàn thành trong Giai đoạn 1)*
  - **Mô tả**: Hiển thị tên bài hát, tên nghệ sĩ, thời gian phát, thanh tiến trình (progress bar) và thumbnail/icon bài hát trên màn hình VuNMix.
  - **Tương tác**: Chạm để Play/Pause, vuốt trái/phải để chuyển bài (Next/Prev), xoay núm để tăng giảm âm lượng ứng dụng nhạc.
  - **Kỹ thuật**: Desktop app đọc metadata từ *Windows System Media Transport Controls (SMTC)* / *Spotify Local API* và gửi gói tin nhị phân `MEDIA_INFO` xuống ESP32-S3 qua USB-CDC.
  - **Ưu tiên**: ⭐⭐⭐⭐⭐ (Cao)

- [x] **2. Tích hợp OBS Studio (OBS Mixer & Stream Deck Controller)** ✅ *(Đã hoàn thành trong Giai đoạn 3)*
  - **Mô tả**: Biến VuNMix thành bàn trộn âm thanh và chuyển cảnh chuyên nghiệp cho Streamer.
  - **Tính năng**:
    - Nhận diện trạng thái **Live / Rec** từ OBS Studio.
    - Hỗ trợ chuyển Scene và điều khiển OBS audio sources.
  - **Kỹ thuật**: Desktop kết nối tới OBS qua module `obs_service.py` (OBS WebSocket v5).
  - **Ưu tiên**: ⭐⭐⭐⭐⭐ (Cao)

- [x] **3. Cấu hình Audio Profiles / Sound Presets (1 Chạm Đổi Chế Độ Âm Thanh)** ✅ *(Đã hoàn thành trong Giai đoạn 3)*
  - **Mô tả**: Tạo các profile âm thanh mẫu trên Desktop và chuyển đổi nhanh trên thiết bị:
    - **Gaming Preset**: Game 100%, Discord 90%, Chrome 20%, Master 80%.
    - **Work / Focus Preset**: Spotify 70%, Chrome 80%, Mute Discord.
    - **Cinema / Movie**: Media 100%, Master 90%, Mic 0%.
    - **Night Mode**: Master tối đa 35%, Mic 50%.
  - **Ưu tiên**: ⭐⭐⭐⭐ (Trung bình)

- [x] **6. Mở rộng Giao diện Đồng hồ Chờ (Custom Clock Faces & Weather Widget)** ✅ *(Đã hoàn thành trong Giai đoạn 3)*
  - **Mô tả**: Bổ sung hiển thị thời tiết thời gian thực và branding status label trên màn hình Clock Standby.
  - **Kỹ thuật**: Desktop lấy thời tiết từ Open-Meteo API qua `weather_service.py`.
  - **Ưu tiên**: ⭐⭐⭐⭐ (Trung bình)

---

## 📡 Nhóm 3: Kết nối Không dây & Tiện ích Phần cứng (Wireless & Bluetooth)

- [ ] **7. Chế độ Điều khiển Không dây qua Wi-Fi (Wireless Mode)**
  - **Mô tả**: Cho phép ESP32-S3 kết nối vào mạng Wi-Fi gia đình, đặt VuNMix ở bất kỳ đâu trên bàn làm việc mà không cần cắm cáp USB vào PC.
  - **Kỹ thuật**: Hỗ trợ chuyển đổi giao thức linh hoạt giữa USB-CDC Serial và WebSocket qua Wi-Fi (UDP/TCP).
  - **Ưu tiên**: ⭐⭐⭐⭐ (Trung bình)

- [ ] **8. Chế độ Bluetooth Media Controller Độc lập**
  - **Mô tả**: Khi không cắm vào PC, VuNMix có thể phát Bluetooth BLE HID để điều khiển âm lượng, chuyển bài hát trực tiếp cho **Điện thoại iPhone / Android, iPad, MacBook hoặc Smart TV**.
  - **Ưu tiên**: ⭐⭐⭐⭐ (Trung bình)

---

## 📊 Bảng Đánh giá & Thứ tự Ưu tiên Triển khai

| STT | Tính năng | Độ phức tạp | Tính khả thi | Trạng thái |
| :---: | :--- | :---: | :---: | :---: |
| 1 | **PC Hardware Monitor (CPU/GPU/RAM/Network)** | Thấp | 100% | ✅ **Đã hoàn thành (Passed)** |
| 2 | **Media Player Info (Spotify / Track Name / Playback)** | Trung bình | 100% | ✅ **Đã hoàn thành (Passed)** |
| 3 | **Audio-Reactive NeoPixel (LED theo beat nhạc)** | Thấp | 100% | ✅ **Đã hoàn thành (Passed)** |
| 4 | **Stereo L/R VU Meter & Header Dual Meter** | Trung bình | 100% | ✅ **Đã hoàn thành (Passed)** |
| 5 | **OBS Studio Stream Deck Integration** | Trung bình | 100% | ✅ **Đã hoàn thành (Passed)** |
| 6 | **Audio Profiles / Sound Presets (1 Chạm)** | Trung bình | 100% | ✅ **Đã hoàn thành (Passed)** |
| 7 | **Custom Clock Faces & Weather Widget** | Trung bình | 100% | ✅ **Đã hoàn thành (Passed)** |
| 8 | **Wireless Wi-Fi & Bluetooth BLE HID Controller** | Cao | 100% | 🚀 **Giai đoạn 4** |
