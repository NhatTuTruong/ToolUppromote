<?php

return [
    'api_token' => env('LICENSE_API_TOKEN', ''),
    'default_daily_limit' => (int) env('LICENSE_DEFAULT_DAILY_LIMIT', 500),
    'max_machines_per_key' => (int) env('LICENSE_MAX_MACHINES_PER_KEY', 2),
];
