package com.nexushestia.athena

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.os.Bundle
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.nexushestia.athena.theme.AthenaTheme

class MainActivity : ComponentActivity() {
    private lateinit var sharedPreferences: SharedPreferences
    private lateinit var offlineQueue: OfflineQueue

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        sharedPreferences = getSharedPreferences("athena_prefs", Context.MODE_PRIVATE)
        offlineQueue = OfflineQueue(this)

        // Start Persistent Background Foreground Service
        startAthenaBackgroundService()

        setContent {
            AthenaTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Color(0xFF070913)
                ) {
                    AthenaAppContainer(sharedPreferences, offlineQueue)
                }
            }
        }
    }

    private fun startAthenaBackgroundService() {
        try {
            val intent = Intent(this, AthenaService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(intent)
            } else {
                startService(intent)
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
@Composable
fun AthenaAppContainer(sharedPreferences: SharedPreferences, offlineQueue: OfflineQueue) {
    val context = LocalContext.current
    var serverUrl by remember { mutableStateOf(sharedPreferences.getString("server_url", "") ?: "") }
    var inputUrl by remember { mutableStateOf(if (serverUrl.isEmpty()) "http://192.168.4.73:5000" else serverUrl) }
    var showWebview by remember { mutableStateOf(serverUrl.isNotEmpty()) }
    
    // Permission requests
    var hasMicPermission by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
    }
    var hasNotificationPermission by remember {
        mutableStateOf(
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
            } else {
                true
            }
        )
    }

    val micLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        hasMicPermission = isGranted
    }

    val notificationLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        hasNotificationPermission = isGranted
    }

    // Launch permission requests
    LaunchedEffect(Unit) {
        if (!hasMicPermission) {
            micLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !hasNotificationPermission) {
            notificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    if (!showWebview) {
        Box(
            modifier = Modifier.fillMaxSize().background(Color(0xFF070913)),
            contentAlignment = Alignment.Center
        ) {
            Column(
                modifier = Modifier
                    .padding(24.dp)
                    .fillMaxWidth()
                    .border(1.dp, Color(0xFF9D4EDD).copy(alpha = 0.3f), RoundedCornerShape(16.dp))
                    .background(Color(0xFF0D1121).copy(alpha = 0.9f), RoundedCornerShape(16.dp))
                    .padding(28.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                Text(
                    text = "ATHENA MOBILE",
                    color = Color(0xFF00D2FF),
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.SansSerif,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
                Text(
                    text = "Sovereignty Client Portal",
                    color = Color(0xFF94A3B8),
                    fontSize = 12.sp,
                    modifier = Modifier.padding(bottom = 24.dp)
                )

                OutlinedTextField(
                    value = inputUrl,
                    onValueChange = { inputUrl = it },
                    label = { Text("Athena Core Server URL", color = Color(0xFF94A3B8)) },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = Color.White,
                        unfocusedTextColor = Color.White,
                        focusedBorderColor = Color(0xFF00D2FF),
                        unfocusedBorderColor = Color(0xFF94A3B8).copy(alpha = 0.4f),
                        focusedLabelColor = Color(0xFF00D2FF),
                        cursorColor = Color(0xFF00D2FF)
                    ),
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(24.dp))

                Button(
                    onClick = {
                        val cleanedUrl = if (!inputUrl.startsWith("http://") && !inputUrl.startsWith("https://")) {
                            "http://$inputUrl"
                        } else {
                            inputUrl
                        }
                        sharedPreferences.edit().putString("server_url", cleanedUrl).apply()
                        serverUrl = cleanedUrl
                        showWebview = true
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF9D4EDD)),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("CONNECT TO CORE", color = Color.White, fontWeight = FontWeight.Bold)
                }
            }
        }
    } else {
        Box(modifier = Modifier.fillMaxSize()) {
            AndroidView(
                factory = { ctx ->
                    WebView(ctx).apply {
                        webViewClient = object : WebViewClient() {
                            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                                return false
                            }
                        }
                        webChromeClient = object : WebChromeClient() {
                            override fun onPermissionRequest(request: PermissionRequest) {
                                for (resource in request.resources) {
                                    if (PermissionRequest.RESOURCE_AUDIO_CAPTURE == resource) {
                                        request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                                        return
                                    }
                                }
                                super.onPermissionRequest(request)
                            }
                        }
                        
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        settings.databaseEnabled = true
                        settings.mediaPlaybackRequiresUserGesture = false
                        
                        // Add Javascript Interface for Sovereignty integration (Offline Queue & Voice)
                        addJavascriptInterface(object {
                            @JavascriptInterface
                            fun queueOfflineDictation(text: String) {
                                offlineQueue.queueDictation(text)
                                Toast.makeText(context, "Offline: Saved dictation locally", Toast.LENGTH_SHORT).show()
                            }

                            @JavascriptInterface
                            fun isNetworkAvailable(): Boolean {
                                val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
                                val activeNetwork = cm.activeNetwork ?: return false
                                val capabilities = cm.getNetworkCapabilities(activeNetwork) ?: return false
                                return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                            }
                        }, "AndroidInterface")

                        loadUrl(serverUrl)
                    }
                },
                modifier = Modifier.fillMaxSize(),
                update = { webView ->
                    if (webView.url != serverUrl) {
                        webView.loadUrl(serverUrl)
                    }
                }
            )

            // Reset Connection floating button
            Box(
                modifier = Modifier.fillMaxSize().padding(16.dp),
                contentAlignment = Alignment.BottomEnd
            ) {
                Button(
                    onClick = {
                        sharedPreferences.edit().remove("server_url").apply()
                        serverUrl = ""
                        showWebview = false
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFF0D1121).copy(alpha = 0.85f),
                        contentColor = Color(0xFFFF0055)
                    ),
                    modifier = Modifier.border(1.dp, Color(0xFFFF0055).copy(alpha = 0.4f), RoundedCornerShape(18.dp)),
                    contentPadding = PaddingValues(horizontal = 14.dp, vertical = 8.dp),
                    shape = RoundedCornerShape(18.dp)
                ) {
                    Text(
                        text = "RESET IP", 
                        fontSize = 10.sp, 
                        fontWeight = FontWeight.Bold, 
                        fontFamily = FontFamily.Monospace
                    )
                }
            }
        }
    }
}
