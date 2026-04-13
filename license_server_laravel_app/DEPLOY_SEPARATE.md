# Deploy riêng Laravel license server

## 1) Mang source Laravel đi deploy

Copy thư mục `license_server_laravel_app/` sang repo/server riêng.

## 2) Cài đặt server

```bash
composer install --no-dev --optimize-autoloader
cp .env.mysql.example .env
php artisan key:generate
php artisan migrate --force
```

Import key:

```bash
php artisan license:import-keys "/path/vendor_keys_AFL1.txt" --daily-limit=500 --max-machines=2
```

## 3) Chạy service

Dev:

```bash
php artisan serve --host=0.0.0.0 --port=8090
```

Production: dùng nginx/apache + php-fpm, bật HTTPS.

## 4) Cấu hình tool Python

Trong `.env` của tool:

```env
AFF_LICENSE_API_BASE_URL=https://license.your-domain.com
AFF_LICENSE_API_TOKEN=your-strong-token
AFF_LICENSE_DAILY_LIMIT=500
```

Tool Python không cần source Laravel ở local.
