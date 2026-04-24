<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::table('license_keys', function (Blueprint $table): void {
            $table->json('allowed_sources')->nullable()->after('max_machines');
        });

        DB::table('license_keys')
            ->whereNull('allowed_sources')
            ->update(['allowed_sources' => json_encode(['uppromote', 'goaffpro'])]);
    }

    public function down(): void
    {
        Schema::table('license_keys', function (Blueprint $table): void {
            $table->dropColumn('allowed_sources');
        });
    }
};

