plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Version de l'appli : EVA la compare à celle qu'elle sert pour proposer la mise à jour.
val versionEva = 3

android {
    namespace = "fr.eva.satellite"
    compileSdk = 34

    defaultConfig {
        applicationId = "fr.eva.satellite"
        minSdk = 26
        targetSdk = 34
        versionCode = versionEva
        versionName = "1.0.$versionEva"
    }

    // Signature : la clé est fournie par l'environnement (secrets GitHub) ou présente à côté de ce fichier.
    // Sans clé (fork, compilation locale), l'APK est signée avec la clé de débogage.
    val cleFichier = file(System.getenv("EVA_KEYSTORE_FILE") ?: "eva-satellite.jks")
    val cleMotDePasse = System.getenv("EVA_KEYSTORE_PASSWORD") ?: ""
    signingConfigs {
        create("eva") {
            storeFile = cleFichier
            storePassword = cleMotDePasse
            keyAlias = System.getenv("EVA_KEY_ALIAS") ?: "eva"
            keyPassword = System.getenv("EVA_KEY_PASSWORD") ?: cleMotDePasse
        }
    }

    buildFeatures { compose = true }
    composeOptions { kotlinCompilerExtensionVersion = "1.5.14" }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = if (cleFichier.exists() && cleMotDePasse.isNotEmpty()) signingConfigs.getByName("eva") else signingConfigs.getByName("debug")
        }
    }
    lint {
        checkReleaseBuilds = false
        abortOnError = false
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("androidx.activity:activity-compose:1.9.1")
    implementation(platform("androidx.compose:compose-bom:2024.06.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
