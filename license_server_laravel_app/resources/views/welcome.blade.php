<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <title>{{ config('app.name', 'License Server') }}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,600;0,9..40,700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ asset('css/admin-theme.css') }}">
</head>
<body class="admin-body login-page">
    <div class="login-card login-card-wide">
        <div class="login-brand">
            <div class="login-brand-mark" aria-hidden="true">L</div>
            <div>
                <h1>{{ config('app.name', 'License Server') }}</h1>
                <p>API kích hoạt &amp; quản trị key bản quyền</p>
            </div>
        </div>
        <p class="muted" style="margin: 0 0 20px; line-height: 1.55;">
            Trang mặc định của ứng dụng. Thông thường bạn sẽ dùng trang quản trị hoặc API theo tài liệu triển khai.
        </p>
        <a href="{{ route('admin.login') }}" class="login-submit">Đăng nhập quản trị</a>
        <p class="login-foot">Laravel {{ app()->version() }}</p>
    </div>
</body>
</html>
