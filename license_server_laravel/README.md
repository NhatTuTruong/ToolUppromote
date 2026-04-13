# Laravel License Server

Source này là backend quản lý key/activation cho app Python.

## 1) Khởi tạo project Laravel

```bash
composer create-project laravel/laravel license_server_laravel
```

Sau đó copy các file trong thư mục này vào đúng vị trí tương ứng trong project Laravel vừa tạo.

## 2) Cấu hình `.env`

```env
APP_NAME=LicenseServer
APP_ENV=production
APP_KEY=
APP_DEBUG=false
APP_URL=https://license.your-domain.com

DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=aff_license
DB_USERNAME=aff_license
DB_PASSWORD=secret

LICENSE_API_TOKEN=replace-with-strong-token
LICENSE_DEFAULT_DAILY_LIMIT=500
LICENSE_MAX_MACHINES_PER_KEY=2
```

## 3) Chạy migration

```bash
php artisan key:generate
php artisan migrate
```

## 4) API dùng cho Python

- `POST /api/v1/licenses/activate`
- `POST /api/v1/licenses/deactivate`
- `POST /api/v1/licenses/validate`
- `GET /api/v1/licenses/health`

Header cho các API POST:

```http
Authorization: Bearer {LICENSE_API_TOKEN}
Content-Type: application/json
```

## 5) Cấu hình Python app

Trong `.env` của app Python:

```env
AFF_LICENSE_API_BASE_URL=https://license.your-domain.com
AFF_LICENSE_API_TOKEN=replace-with-strong-token
AFF_LICENSE_DAILY_LIMIT=500
```
