package com.nexushestia.athena

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

class OfflineQueue(private val context: Context) : SQLiteOpenHelper(context, DATABASE_NAME, null, DATABASE_VERSION) {

    companion object {
        private const val DATABASE_NAME = "athena_offline.db"
        private const val DATABASE_VERSION = 1
        private const val TABLE_DICTATIONS = "offline_dictations"
        private const val KEY_ID = "id"
        private const val KEY_TEXT = "text"
        private const val KEY_TIMESTAMP = "timestamp"
        private const val TAG = "AthenaOfflineQueue"
    }

    override fun onCreate(db: SQLiteDatabase?) {
        val createTable = ("CREATE TABLE " + TABLE_DICTATIONS + "("
                + KEY_ID + " INTEGER PRIMARY KEY AUTOINCREMENT,"
                + KEY_TEXT + " TEXT,"
                + KEY_TIMESTAMP + " INTEGER" + ")")
        db?.execSQL(createTable)
        Log.d(TAG, "Offline dictations table created.")
    }

    override fun onUpgrade(db: SQLiteDatabase?, oldVersion: Int, newVersion: Int) {
        db?.execSQL("DROP TABLE IF EXISTS $TABLE_DICTATIONS")
        onCreate(db)
    }

    fun queueDictation(text: String) {
        try {
            val db = this.writableDatabase
            val values = ContentValues().apply {
                put(KEY_TEXT, text)
                put(KEY_TIMESTAMP, System.currentTimeMillis())
            }
            db.insert(TABLE_DICTATIONS, null, values)
            db.close()
            Log.d(TAG, "Successfully queued offline dictation: $text")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to queue offline dictation", e)
        }
    }

    fun getUnsyncedDictations(): List<DictationItem> {
        val list = mutableListOf<DictationItem>()
        try {
            val selectQuery = "SELECT * FROM $TABLE_DICTATIONS ORDER BY $KEY_TIMESTAMP ASC"
            val db = this.readableDatabase
            val cursor = db.rawQuery(selectQuery, null)
            if (cursor.moveToFirst()) {
                do {
                    val id = cursor.getInt(cursor.getColumnIndexOrThrow(KEY_ID))
                    val text = cursor.getString(cursor.getColumnIndexOrThrow(KEY_TEXT))
                    val timestamp = cursor.getLong(cursor.getColumnIndexOrThrow(KEY_TIMESTAMP))
                    list.add(DictationItem(id, text, timestamp))
                } while (cursor.moveToNext())
            }
            cursor.close()
            db.close()
        } catch (e: Exception) {
            Log.e(TAG, "Error querying unsynced items", e)
        }
        return list
    }

    fun deleteDictations(ids: List<Int>) {
        try {
            val db = this.writableDatabase
            for (id in ids) {
                db.delete(TABLE_DICTATIONS, "$KEY_ID = ?", arrayOf(id.toString()))
            }
            db.close()
            Log.d(TAG, "Deleted processed offline items: $ids")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to delete offline items", e)
        }
    }

    fun attemptSync(serverUrl: String, onSyncComplete: (Boolean, Int) -> Unit) {
        val items = getUnsyncedDictations()
        if (items.isEmpty()) {
            onSyncComplete(true, 0)
            return
        }

        if (!isNetworkAvailable()) {
            Log.d(TAG, "Sync aborted: No network connectivity.")
            onSyncComplete(false, 0)
            return
        }

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val cleanUrl = serverUrl.trimEnd('/')
                val urlObj = URL("$cleanUrl/api/offline/sync")
                val conn = urlObj.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json; utf-8")
                conn.setRequestProperty("Accept", "application/json")
                
                // Retrieve and add authentication headers
                val prefs = context.getSharedPreferences("athena_prefs", Context.MODE_PRIVATE)
                val passcode = prefs.getString("athena_passcode", null)
                if (passcode != null) {
                    conn.setRequestProperty("Authorization", "Bearer $passcode")
                    conn.setRequestProperty("X-Athena-Token", passcode)
                }

                conn.doOutput = true
                conn.connectTimeout = 8000
                conn.readTimeout = 8000

                // Build JSON payload
                val jsonArray = JSONArray()
                for (item in items) {
                    val itemJson = JSONObject().apply {
                        put("id", item.id)
                        put("text", item.text)
                        put("timestamp", item.timestamp)
                    }
                    jsonArray.put(itemJson)
                }
                
                val payload = JSONObject().apply {
                    put("items", jsonArray)
                }

                OutputStreamWriter(conn.outputStream, "UTF-8").use { writer ->
                    writer.write(payload.toString())
                    writer.flush()
                }

                val responseCode = conn.responseCode
                if (responseCode == HttpURLConnection.HTTP_OK) {
                    val idsToDelete = items.map { it.id }
                    deleteDictations(idsToDelete)
                    Log.d(TAG, "Synchronized and cleared ${items.size} dictation(s).")
                    onSyncComplete(true, items.size)
                } else {
                    Log.e(TAG, "Sync failed with HTTP error: $responseCode")
                    onSyncComplete(false, 0)
                }
                conn.disconnect()
            } catch (e: Exception) {
                Log.e(TAG, "Sync networking error", e)
                onSyncComplete(false, 0)
            }
        }
    }

    private fun isNetworkAvailable(): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val activeNetwork = cm.activeNetwork ?: return false
        val capabilities = cm.getNetworkCapabilities(activeNetwork) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    data class DictationItem(val id: Int, val text: String, val timestamp: Long)
}
