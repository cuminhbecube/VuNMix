# VuNMix v0.5.0

## Tám giao diện thiết bị, chọn từ app PC

Mở **Device → Appearance**, chọn mẫu rồi bấm **Save settings**:

- **Classic**: giao diện mặc định hiện tại.
- **Windows Dark**: bố cục tối theo đề xuất trước.
- **Studio**: phong cách thiết bị âm thanh và thang phần trăm.
- **Paper**: nền ngà, chữ lớn và đường nhấn đỏ.
- **Orbit**: vòng đo cyan và thanh chế độ dọc.
- **Pixel**: LCD cổ điển, chữ pixel và hình khối vuông.
- **Blocks**: mảng cobalt, cam, kem với số lớn.
- **Terminal**: bảng điều khiển xanh phosphor và thanh phân đoạn.

Ảnh xem trước lấy từ chính mã vẽ firmware ở độ phân giải **320×240**.
Thiết bị ghi nhớ giao diện đã chọn sau khi khởi động lại. App giữ lựa chọn
đã lưu và đồng bộ lại sau khi kết nối; việc xem thử không gửi lệnh xuống thiết bị.

## Giữ nguyên cả 16 mặt clock

Không thay đổi bố cục, màu, font, chữ, mặt đồng hồ hoặc ảnh preview clock
hiện có. Không thêm tên theme, logo hay dòng trạng thái vào clock. Kiểu clock
được chọn độc lập trong trang **Clock**, với các ID 0–15 như trước.

Đổi theme khi đang hiện clock hoặc ngủ chỉ lưu lựa chọn. Giao diện mới xuất
hiện khi thiết bị quay về màn điều khiển theo luồng hiện tại, không đánh thức
màn hình hoặc đặt lại thời gian chờ.

## Đồng bộ và tương thích

- Giao thức theme có phản hồi gắn với từng yêu cầu, phân biệt đã áp dụng,
  đã lưu nhưng đang chờ thoát clock/sleep, lỗi và chưa được hỗ trợ.
- App không coi một lần ghi serial hoặc heartbeat OK là xác nhận đã đổi theme.
- Giữ nguyên SETTINGS 19 byte, protocol v1 và các lệnh âm thanh/clock cũ.
- Firmware cũ vẫn kết nối và điều khiển âm thanh/clock; cập nhật cả app và
  firmware lên v0.5.0 để dùng bộ chọn tám giao diện.
- Chỉ một giao diện vận hành được dựng mỗi lần; dữ liệu volume, mute,
  default device, Game A/B, media và thông số PC tiếp tục cập nhật trực tiếp.

## Các lỗi giao diện được sửa

- Tách tên ứng dụng và số âm lượng trong Game Mixer của Classic để không
  chồng chữ.
- Giữ đủ chỗ cho giá trị 100%, tên dài và thông tin media trên các mẫu mới.
- Bộ chọn theme trên PC tự thu gọn ở cửa sổ thấp, giữ đúng tỷ lệ ảnh 4:3.
- Lưu riêng theme không gửi lại trạng thái âm thanh hoặc thay đổi các byte
  thiết lập clock/thời gian chờ đã lưu.

## Kiểm chứng và tệp tải

Release có gate native LVGL so sánh 16 clock gốc tại bốn mốc giờ, kiểm tra
đổi theme liên tục, ảnh preview đóng gói, giao thức và các kiểm thử desktop.
Firmware ESP32-S3 và app Windows được build từ cùng mã nguồn release.

- `VuNMix-Windows-Setup-0.5.0.exe`: bộ cài Windows.
- `VuNMix-Windows-Portable-0.5.0.zip`: bản chạy không cần cài đặt.
- `VuNMix-Firmware-0.5.0.bin`: application image để cập nhật bằng app.
- `VuNMix-Firmware-Full-0.5.0.zip`: các image dùng cho nạp đầy đủ.
- `SHA256SUMS.txt`: mã kiểm tra các tệp phát hành.

Các phép thử tự động và renderer native không thay thế phép đo trên thiết bị
vật lý. Chưa có xác nhận thử trên một thiết bị ESP32-S3 thật trong phiên làm việc này.
