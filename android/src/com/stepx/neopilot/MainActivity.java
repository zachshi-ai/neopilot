package com.stepx.neopilot;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;

/**
 * NeoPilot 原生外壳。
 *
 * 数据有两路来源，页面优先用前者：
 *   1. getLive()  设备本地实时采集（电量 / 定位 / 天气 / 日程）——打开即当下
 *   2. getData()  云端定时推来的快照，作为本地采集不可用时的兜底
 *
 * 桥接全部只读，页面拿不到任何写文件或执行命令的能力。
 */
public class MainActivity extends Activity {

    private static final String SNAPSHOT_NAME = "data.json";
    private static final int REQ_PERMS = 1001;
    private static final String[] WANTED = new String[]{
            Manifest.permission.READ_CALENDAR,
            Manifest.permission.ACCESS_COARSE_LOCATION
    };

    private WebView web;
    private LocalProbe probe;

    private class Bridge {
        @JavascriptInterface
        public String getLive() {
            return probe == null ? "" : probe.getCached();
        }

        @JavascriptInterface
        public String getData() {
            return readSnapshot();
        }

        @JavascriptInterface
        public String getMeta() {
            File f = snapshotFile();
            return "{\"present\":" + f.exists() + ",\"size\":" + (f.exists() ? f.length() : 0) + "}";
        }
    }

    private File snapshotFile() {
        File dir = getExternalFilesDir(null);
        if (dir == null) dir = getFilesDir();
        return new File(dir, SNAPSHOT_NAME);
    }

    private String readSnapshot() {
        File f = snapshotFile();
        if (!f.exists()) return "";
        InputStream in = null;
        try {
            in = new FileInputStream(f);
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) bos.write(buf, 0, n);
            return bos.toString("UTF-8");
        } catch (Exception e) {
            return "";
        } finally {
            if (in != null) try { in.close(); } catch (Exception ignored) {}
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            getWindow().setStatusBarColor(Color.parseColor("#3370FF"));
            getWindow().setNavigationBarColor(Color.parseColor("#F5F6F7"));
        }

        probe = new LocalProbe(this);

        web = new WebView(this);
        web.setLayoutParams(new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        web.setBackgroundColor(Color.parseColor("#F5F6F7"));

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setTextZoom(100);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }

        web.addJavascriptInterface(new Bridge(), "NeoPilotNative");
        web.setWebViewClient(new WebViewClient());
        web.setWebChromeClient(new WebChromeClient());

        setContentView(web);
        web.loadUrl("file:///android_asset/index.html");

        ensurePermissions();
        refreshLive();
    }

    private void ensurePermissions() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return;
        boolean missing = false;
        for (String p : WANTED) {
            if (checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED) missing = true;
        }
        if (missing) requestPermissions(WANTED, REQ_PERMS);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
        super.onRequestPermissionsResult(code, perms, results);
        if (code == REQ_PERMS) refreshLive();
    }

    /** 后台采集一次，完成后让页面重新取数。 */
    private void refreshLive() {
        if (probe == null) return;
        probe.refresh(new LocalProbe.Callback() {
            @Override
            public void onDone() {
                if (web == null) return;
                web.post(new Runnable() {
                    @Override
                    public void run() {
                        if (web != null) {
                            web.evaluateJavascript(
                                    "window.NeoPilotRefresh && window.NeoPilotRefresh()", null);
                        }
                    }
                });
            }
        });
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshLive();
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && web != null && web.canGoBack()) {
            web.goBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.loadUrl("about:blank");
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
