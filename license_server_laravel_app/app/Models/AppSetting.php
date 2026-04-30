<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class AppSetting extends Model
{
    public $timestamps = false;

    protected $fillable = [
        'key',
        'value',
    ];

    public static function getValue(string $key, ?string $default = null): ?string
    {
        $value = self::query()->where('key', $key)->value('value');
        if ($value === null) {
            return $default;
        }

        return (string) $value;
    }
}
