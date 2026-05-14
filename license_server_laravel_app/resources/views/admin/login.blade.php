<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <title>Đăng nhập — License Admin</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ asset('css/admin-theme.css') }}">
</head>
<body class="admin-body login-page">
    <div class="login-card">
        <div class="login-brand">
            <div class="login-brand-mark" aria-hidden="true">L</div>
            <div>
                <h1>License Admin</h1>
                <p>Đăng nhập để quản lý key &amp; kích hoạt</p>
            </div>
        </div>
        @if(session('error'))
            <div class="login-error" role="alert">{{ session('error') }}</div>
        @endif
        <form method="post" action="{{ route('admin.login.submit') }}">
            @csrf
            <label class="field-label" for="password">Mật khẩu admin</label>
            <input id="password" name="password" type="password" required autocomplete="current-password" placeholder="••••••••">
            <button type="submit" class="login-submit">Đăng nhập</button>
        </form>
        <p class="login-foot">Kết nối an toàn — chỉ dùng trong mạng nội bộ / HTTPS khi triển khai.</p>
    </div>
</body>
</html>
