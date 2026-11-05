# Đăng nhập / đăng ký Google qua Supabase

Hai nút Google dùng chung `signInWithOAuth({ provider: 'google' })`. Supabase tạo tài khoản khi đăng nhập lần đầu; trigger hiện có tạo profile. Khi quay về `/auth/callback`, SDK nhận session, ứng dụng chuyển đến `/home` và auth listener tải profile/preferences. Tài khoản chưa hoàn thành onboarding sẽ được hỏi thông tin như luồng đăng ký email. Khi người dùng hủy hoặc provider trả lỗi, trang callback hiển thị lỗi và liên kết quay lại.

## Cấu hình bắt buộc trên dashboard

1. Google Cloud Console: cấu hình OAuth consent screen, tạo OAuth client loại **Web application**. Nếu ứng dụng đang ở chế độ Testing, thêm tài khoản thử vào Test users.
2. Trong **Authorized redirect URIs** của Google client, thêm callback URL hiển thị tại Supabase → Authentication → Sign In / Providers → Google, thường là `https://<project-ref>.supabase.co/auth/v1/callback`.
3. Bật Google provider trong Supabase, nhập Google Client ID và Client Secret rồi lưu. Client Secret chỉ nằm trong cấu hình provider, không đưa vào biến môi trường frontend.
4. Supabase → Authentication → URL Configuration: đặt Site URL của frontend; thêm `http://localhost:5173/auth/callback` vào Redirect URLs, cùng URL tương ứng của bản deploy. Nếu dùng cổng khác, thêm đúng origin đó.
5. Frontend dùng `VITE_SUPABASE_URL` và `VITE_SUPABASE_PUBLISHABLE_KEY` hiện có trong `.env.local`.

## Kiểm tra thực tế

- Bấm Google ở cả đăng nhập và đăng ký: chọn tài khoản, xác nhận, quay lại `/home` với tài khoản thật.
- Hoàn thành onboarding, đăng xuất rồi đăng nhập lại: preferences đã lưu được tải lại.
- Hủy tại Google: callback báo lỗi và cho phép quay lại thử.
- Tải lại `/home`: session vẫn được SDK khôi phục.

Test tự động dùng mock; cần cấu hình dashboard và tài khoản Google để xác minh toàn bộ luồng thực tế.

Tài liệu: [Supabase Google Auth](https://supabase.com/docs/guides/auth/social-login/auth-google), [signInWithOAuth](https://supabase.com/docs/reference/javascript/auth-signinwithoauth).
