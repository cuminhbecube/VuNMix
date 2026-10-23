# VuNMix v0.4.32

Bản vá tập trung vào mất kết nối USB, cập nhật Desktop/firmware, cảm ứng và
audio automation. Giao thức USB vẫn là phiên bản 1; không đổi chân phần cứng
hay định dạng cấu hình hiện có.

## Các lỗi được sửa

- **USB/reconnect:** transport dùng trong ứng dụng Desktop nhận đúng tham số
  `expected_connection` khi đọc/ghi lỗi. Lỗi đến muộn từ một kết nối cũ không
  đóng kết nối thay thế hoặc xóa thời gian kết nối của thiết bị mới.
- **Treo khi mất USB và đang gửi icon:** giải phóng khóa ghi serial trước khi
  gọi callback disconnect, tránh chờ vòng giữa khóa ghi và bộ nhớ đệm icon.
- **Cập nhật Desktop và firmware đồng thời:** hai luồng dùng chung một cơ chế
  giữ quyền cập nhật. Desktop giữ quyền từ lúc tải installer đến khi bàn giao
  và thoát; firmware giữ quyền trong quá trình flash và xác minh reconnect.
- **Yêu cầu cập nhật Desktop trùng nhau:** chặn yêu cầu thứ hai từ Settings
  hoặc system tray khi cập nhật đang chạy. Mỗi lần tải có tệp tạm riêng, nên
  lỗi dọn dẹp của một lần tải không xóa dữ liệu của lần khác.
- **Tắt Auto Firmware Update khi đang chờ:** kiểm tra lại cấu hình sau thời
  gian chờ kết nối, sau truy vấn release, khi chạy callback UI, sau tải và
  ngay trước khi flash. Việc ghi firmware đã bắt đầu được phép hoàn tất.
- **Cảm ứng phát lệnh trùng:** bộ giải mã gesture phần cứng và tọa độ dùng
  chung trạng thái của một lần chạm. Double tap chỉ tạo lệnh mute/unmute;
  nhấn giữ chỉ phát một lần, kể cả khi giữ ngón tay thêm hoặc nhận nhiều IRQ.
- **Ducking ghi đè mute thủ công:** ducking chỉ ghi âm lượng, không ghi mute
  vào Windows. Thao tác mute/unmute của người dùng được giữ trong attack,
  release, tắt tính năng, thoát ứng dụng và khôi phục sau crash, kể cả khi
  trạng thái lưu trong bộ nhớ chưa kịp cập nhật.
- **Quên route sau lỗi cleanup:** route chỉ bị xóa khỏi danh sách theo dõi
  khi Windows xác nhận xóa thành công. Lỗi tạm thời được thử lại ở vòng xử lý
  tiếp theo; cleanup và áp dụng route được tuần tự hóa.

## Thay đổi cảm nhận khi sử dụng

Single tap được xác nhận sau cửa sổ double tap **350 ms** tính từ lúc nhả
ngón tay. Nếu lần chạm thứ hai bắt đầu trong cửa sổ này, firmware đợi kết
thúc lần chạm đó để phân biệt double tap với vuốt/nhấn giữ. Nhờ vậy double
tap không vô tình chuyển Navigate/Edit hoặc đổi thiết bị mặc định trước
khi mute.

## Kiểm tra hồi quy

- `test_serial_disconnect_regressions.py`: transport thực tế của Desktop,
  lỗi đọc/ghi, kết nối thay thế và tranh chấp gửi icon khi mất USB.
- `test_update_lifecycle.py`: loại trừ cập nhật theo cả hai chiều, yêu cầu
  trùng, lỗi tải/tạo thread, hủy Auto Firmware Update và tệp tải tạm riêng.
- `test_touch_gestures_firmware.py`: biên dịch `Input.cpp` và các hàm dispatch
  thực tế với I/O mô phỏng; kiểm tra tap, double tap, long press, wake,
  vuốt, gesture hỗn hợp và tràn bộ đếm thời gian.
- `test_audio_automation.py` và `test_audio_volume_only.py`: mute thực tế
  khác với cache, khôi phục volume và thử lại việc xóa route bị lỗi.

Pipeline release tiếp tục yêu cầu feature contracts, bộ test Desktop trên
Windows, build ESP32-S3, đóng gói Windows và năm vòng connection/crash stress
trước khi xuất bản các asset cùng `SHA256SUMS.txt`.

Các phép thử ở trên dùng I/O mô phỏng cho lỗi kết nối và thao tác cảm ứng.
Chúng không thay thế kiểm thử trên board ESP32-S3/CST816S thật; theo dõi các
bài thử đó trong [Hardware QA Matrix](hardware-qa-matrix.md).
