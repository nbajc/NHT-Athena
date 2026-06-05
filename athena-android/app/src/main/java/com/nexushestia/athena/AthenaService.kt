package com.nexushestia.athena

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkRequest
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat

class AthenaService : Service() {

    companion object {
        private const val TAG = "AthenaPersistentService"
        private const val CHANNEL_ID = "athena_foreground_service"
        private const val CHANNEL_NAME = "Athena Sovereignty Engine"
        private const val NOTIFICATION_ID = 4774
    }

    private lateinit var offlineQueue: OfflineQueue
    private lateinit var connectivityManager: ConnectivityManager
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "Athena background persistence service created.")
        offlineQueue = OfflineQueue(this)
        connectivityManager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        startForegroundServiceNotification()
        setupNetworkMonitoring()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "Athena service start command received.")
        // Keep running until explicitly stopped
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }

    private fun startForegroundServiceNotification() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps Athena active to sync offline dictations and receive messages"
            }
            manager.createNotificationChannel(channel)
        }

        val intent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .setContentTitle("Athena Sovereignty Agent")
            .setContentText("Athena is active in the background")
            .setContentIntent(pendingIntent)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()

        startForeground(NOTIFICATION_ID, notification)
    }

    private fun setupNetworkMonitoring() {
        val request = NetworkRequest.Builder().build()
        networkCallback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                super.onAvailable(network)
                Log.d(TAG, "Network connection restored. Syncing offline queue...")
                
                // Fetch server URL from preferences
                val prefs = getSharedPreferences("athena_prefs", Context.MODE_PRIVATE)
                val serverUrl = prefs.getString("server_url", "") ?: ""
                
                if (serverUrl.isNotEmpty()) {
                    offlineQueue.attemptSync(serverUrl) { success, count ->
                        if (success && count > 0) {
                            Log.d(TAG, "Synced $count offline dictations on network reconnect.")
                        }
                    }
                }
            }
        }
        
        try {
            connectivityManager.registerNetworkCallback(request, networkCallback!!)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to register network callback", e)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "Athena background service destroyed.")
        networkCallback?.let {
            try {
                connectivityManager.unregisterNetworkCallback(it)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to unregister callback", e)
            }
        }
    }
}
