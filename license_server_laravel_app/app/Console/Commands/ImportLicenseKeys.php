<?php

namespace App\Console\Commands;

use App\Models\LicenseKey;
use Illuminate\Console\Command;

class ImportLicenseKeys extends Command
{
    protected $signature = 'license:import-keys {file : Path to txt file} {--daily-limit=500} {--max-machines=2}';

    protected $description = 'Import license keys from txt file (one key per line)';

    public function handle(): int
    {
        $path = (string) $this->argument('file');
        if (!is_file($path)) {
            $this->error("File not found: {$path}");
            return self::FAILURE;
        }

        $lines = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        if (!$lines) {
            $this->warn('No keys found.');
            return self::SUCCESS;
        }

        $dailyLimit = max(1, (int) $this->option('daily-limit'));
        $maxMachines = max(1, (int) $this->option('max-machines'));

        $created = 0;
        $updated = 0;
        foreach ($lines as $line) {
            $key = strtoupper(trim((string) $line));
            if ($key === '' || str_starts_with($key, '#')) {
                continue;
            }
            $model = LicenseKey::query()->firstOrNew(['license_key' => $key]);
            $isNew = !$model->exists;
            $model->key_hint = substr($key, -6);
            $model->status = $model->status ?: 'active';
            $model->daily_limit = $model->daily_limit ?: $dailyLimit;
            $model->max_machines = $model->max_machines ?: $maxMachines;
            $model->save();
            if ($isNew) {
                $created++;
            } else {
                $updated++;
            }
        }

        $this->info("Done. created={$created}, updated={$updated}");
        return self::SUCCESS;
    }
}
