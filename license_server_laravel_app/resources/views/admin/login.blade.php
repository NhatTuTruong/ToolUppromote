<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>License Admin Login</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f5f7fb; margin: 0; }
        .box { width: 380px; margin: 80px auto; background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 20px; }
        h1 { margin: 0 0 16px; font-size: 20px; }
        label { display: block; margin-bottom: 6px; font-weight: 600; }
        input { width: 100%; padding: 10px; border: 1px solid #bbb; border-radius: 6px; box-sizing: border-box; }
        button { margin-top: 14px; width: 100%; padding: 10px; background: #0d6efd; color: #fff; border: 0; border-radius: 6px; font-weight: 600; }
        .error { color: #b42318; margin-bottom: 10px; }
    </style>
</head>
<body>
<div class="box">
    <h1>License Admin</h1>
    @if(session('error'))
        <div class="error">{{ session('error') }}</div>
    @endif
    <form method="post" action="{{ route('admin.login.submit') }}">
        @csrf
        <label for="password">Mật khẩu admin</label>
        <input id="password" name="password" type="password" required>
        <button type="submit">Đăng nhập</button>
    </form>
</div>
</body>
</html>
