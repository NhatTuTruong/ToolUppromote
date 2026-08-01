<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::table('license_keys', function (Blueprint $table): void {
            $table->boolean('allow_auto_apply_refersion')->default(false)->after('allow_auto_apply_collabs');
        });

        DB::table('license_keys')
            ->whereNull('allow_auto_apply_refersion')
            ->update(['allow_auto_apply_refersion' => false]);
    }

    public function down(): void
    {
        Schema::table('license_keys', function (Blueprint $table): void {
            $table->dropColumn('allow_auto_apply_refersion');
        });
    }
};
