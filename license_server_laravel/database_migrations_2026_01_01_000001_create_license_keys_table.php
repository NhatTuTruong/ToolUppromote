<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('license_keys', function (Blueprint $table): void {
            $table->id();
            $table->string('license_key', 120)->unique();
            $table->string('key_hint', 30)->nullable();
            $table->string('status', 20)->default('active');
            $table->unsignedInteger('daily_limit')->nullable();
            $table->unsignedInteger('max_machines')->nullable();
            $table->timestamp('expires_at')->nullable();
            $table->text('notes')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('license_keys');
    }
};
