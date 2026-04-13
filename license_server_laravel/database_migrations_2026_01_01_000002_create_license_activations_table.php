<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('license_activations', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('license_key_id')->constrained('license_keys')->cascadeOnDelete();
            $table->uuid('activation_id')->unique();
            $table->string('machine_fingerprint', 128);
            $table->timestamp('activated_at');
            $table->timestamp('deactivated_at')->nullable();
            $table->timestamp('last_seen_at')->nullable();
            $table->json('meta')->nullable();
            $table->timestamps();

            $table->index(['license_key_id', 'machine_fingerprint']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('license_activations');
    }
};
