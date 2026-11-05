# Báo cáo tích hợp Supabase Auth và preferences

## Luồng nghiệp vụ

1. FE đăng ký email/mật khẩu qua Supabase Auth. Trigger `on_auth_user_created` trong schema hiện có tạo `public.profiles` với preferences mặc định `{}`.
2. Nếu Supabase trả về session ngay, FE chuyển đến `/home` và mở onboarding. Nếu cần xác nhận email, FE hiển thị màn riêng với biểu tượng thư màu xanh, địa chỉ nhận email và nút quay lại đăng nhập; sau khi xác nhận và có session, onboarding được mở khi vào ứng dụng.
3. Các bước: thông tin cơ bản → personality → chuyến đi tiếp theo → places → travel style → accommodation → food → wrapping up.
4. Next và Back chỉ thay đổi React state. Không lưu bản nháp vào localStorage hoặc DB. Đóng, nhấn Escape hoặc tải lại trước khi Save sẽ bỏ bản nháp.
5. Chỉ bước wrapping up có nút **Save**. FE đọc preferences hiện tại, gộp các trường onboarding, cập nhật `profiles.preferences`, `profiles.first_name`, `profiles.last_name` và `profiles.full_name` trong một lần UPDATE, lọc theo ID người dùng đăng nhập. Tên nằm ở cột riêng; `firstName`, `lastName`, `email` được loại khỏi preferences. RLS trong schema hiện có kiểm tra chủ sở hữu.
6. Chỉ khi DB xác nhận cập nhật thành công mới hiện màn hoàn tất. Khi lỗi, giữ dữ liệu để thử lại. Nút Save bị khóa trong khi chờ.
7. Đăng nhập lại hoặc tải lại trang sẽ đọc preferences từ DB. Nếu `onboardingComplete` đã là `true`, onboarding không tự mở nữa. Bỏ qua onboarding chỉ đóng trong phiên giao diện hiện tại, không đánh dấu hoàn tất trong DB.

## Cập nhật tên hồ sơ và xác nhận email

- Xác nhận email có màn riêng; lỗi đăng ký thực sự vẫn hiển thị ở form.
- Thêm hai cột `profiles.first_name`, `profiles.last_name`; giữ `full_name` để hiển thị tên đầy đủ. Email vẫn thuộc Supabase Auth.
- Đã chạy migration `backend/supabase/003_profile_names.sql` trên database cấu hình ở máy hiện tại: chuyển tên cũ từ JSON sang cột riêng rồi xóa `firstName`, `lastName`, `email`. Đã kiểm tra số hồ sơ và các preferences còn lại không đổi.
- Đồng bộ schema chuẩn, trigger tạo profile, SQLAlchemy model và FE đọc/lưu tên.
- Database khác đang dùng schema cũ cần chạy riêng migration `003_profile_names.sql` trước khi dùng FE mới. Database mới dùng schema chuẩn đã cập nhật.
- Kiểm tra cập nhật: 18 test FE và 22 test backend liên quan đạt; lint phần thay đổi và Vite build đạt. Chưa thử gửi email đăng ký thật trong lần cập nhật này. TypeScript toàn dự án vẫn còn lỗi cũ ở chat/trip/place như ghi bên dưới.

## Các thay đổi

- Thêm client dùng `@supabase/supabase-js`, lấy cấu hình từ `VITE_SUPABASE_URL` và `VITE_SUPABASE_PUBLISHABLE_KEY`.
- Thay mock auth bằng đăng ký, đăng nhập, đăng xuất thật; SDK quản lý session. Auth listener cập nhật trạng thái FE và đọc hồ sơ sau khi có session.
- Xóa dữ liệu mock auth cũ khi khởi tạo. Mật khẩu không còn được lưu trong Zustand/localStorage của mock store. Không tự chuyển dữ liệu demo vào tài khoản thật.
- Các component và CSS của wizard preferences nằm trong `src/features/preferences/components/`; các import và test dùng cùng đường dẫn này. Giao diện vẫn là wizard dạng modal hiện có.
- Các cửa sổ Account settings, Update my assistant và Personalization đọc dữ liệu từ profile đã tải và ghi DB khi lưu/thay đổi cài đặt, thay cho localStorage dùng chung.
- Quên mật khẩu gửi email phục hồi thật. Khi quay lại từ email phục hồi, mở form đặt mật khẩu mới và gọi `auth.updateUser`.
- Thêm test bằng Vitest và React Testing Library, chạy bằng `npm test`.

## Cấu hình và chạy

`.env.local` trên máy hiện tại đã được tạo từ hai cấu hình công khai có sẵn trong `backend/.env`. File này được Git bỏ qua. Không đưa DATABASE_URL hoặc service role key vào FE.

Trên máy khác, copy `.env.example` thành `.env.local`, điền URL/publishable key của cùng project Supabase rồi chạy:

```sh
npm install
npm run dev
```

Project Supabase cần schema `backend/supabase/schema.sql` đã được triển khai, gồm trigger tạo profile và policies SELECT/UPDATE cho chủ sở hữu. Không chạy lại toàn bộ schema trên DB đã có dữ liệu chỉ để bật tính năng này.

Trong Supabase Authentication → URL Configuration, cấu hình Site URL cho FE và cho phép redirect về `http://localhost:5173/home` khi chạy local; thêm URL tương ứng của môi trường deploy. Nếu Vite chạy ở cổng khác, cấu hình cổng đó. Luồng xác nhận email phụ thuộc thiết lập Confirm email của project.

## Kiểm chứng và giới hạn

- Test tự động dùng Supabase mock: đăng nhập đúng/sai, đăng ký có/không có session, phục hồi session, sự kiện recovery, đăng xuất, chặn lưu chưa đăng nhập, cập nhật đúng user, giữ dữ liệu khi DB lỗi, onboarding không ghi khi Next/Back/đóng, Save ở bước cuối và thử lại sau lỗi.
- `npx vite build` đóng gói FE thành công.
- ESLint trên các file thay đổi và test thành công.
- `npm run build` toàn dự án còn bị chặn bởi lỗi TypeScript trong các file chat/trip/place có sẵn, gồm unused imports/variables và lời gọi tạo chat trong `TripDetail.tsx`. `npm run lint` toàn dự án còn lỗi ở các phần đó. Các file này không được sửa trong phạm vi tích hợp auth.
- Chưa kiểm thử end-to-end với tài khoản/email thật và DB đang chạy. Cần kiểm tra thực tế email confirmation/reset, schema và policies trên project đích.
- Google OAuth đã được tích hợp; xem cấu hình và kiểm tra thực tế tại [google-auth.md](google-auth.md). Apple OAuth chưa được tích hợp.
- Gộp preferences phía client giữ các trường không liên quan trong bản ghi vừa đọc; hai tab cùng cập nhật đồng thời vẫn có thể ghi đè nhau. Chưa thêm cơ chế khóa hoặc merge nguyên tử phía DB.

## Tài liệu đối chiếu

- [Supabase signUp](https://supabase.com/docs/reference/javascript/auth-signup)
- [Supabase auth events](https://supabase.com/docs/reference/javascript/auth-onauthstatechange)
- [Supabase password recovery](https://supabase.com/docs/reference/javascript/auth-resetpasswordforemail)
