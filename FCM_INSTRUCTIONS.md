# How to Enable Firebase Push Notifications (FCM)

To wire up FCM push notifications for morning briefings between the Flask backend (`app.py`) and the Android client app:

## Step 1: Set up Firebase Project
1. Open the [Firebase Console](https://console.firebase.google.com/).
2. Click **Add project** and name it **Athena Mobile** (or select an existing project).
3. (Optional) Disable Google Analytics to comply with Sovereignty Guardrails.
4. Click **Create project**.

## Step 2: Register Android Application
1. Click the **Android icon** on the Project Overview page to add an app.
2. In **Android package name**, enter: `com.nexushestia.athena` (must match the Kotlin namespace).
3. In **App nickname**, enter: `Athena Client`.
4. Click **Register app**.

## Step 3: Add Configuration Files
1. Download the `google-services.json` file.
2. Copy `google-services.json` into the app directory of your Android project:
   `athena-android/app/google-services.json`
3. Click **Next** on the Firebase Console.

## Step 4: Configure Android Build Files
We will automatically configure the build scripts in our Android build step. In case you need to verify, these lines will be added:
1. Project-level `build.gradle.kts`:
   ```kotlin
   plugins {
       alias(libs.plugins.google.services) apply false
   }
   ```
2. App-level `build.gradle.kts`:
   ```kotlin
   plugins {
       alias(libs.plugins.google.services)
   }
   dependencies {
       implementation(platform("com.google.firebase:firebase-bom:33.1.0"))
       implementation("com.google.firebase:firebase-messaging-ktx")
   }
   ```

## Step 5: Configure Backend FCM credentials
1. In the Firebase Console, go to **Project Settings** (gear icon next to Project Overview).
2. Open the **Service Accounts** tab.
3. Click **Generate new private key** (downloads a `.json` file).
4. Save the JSON content to your environment variables on Railway:
   - Variable Name: `FIREBASE_CREDENTIALS_JSON`
   - Value: (Paste the entire content of the downloaded JSON file)
5. The backend code in `app.py` is configured to read this environment variable and initialize `firebase-admin` automatically to broadcast updates.
