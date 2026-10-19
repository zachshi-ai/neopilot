package com.stepx.neopilot;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.location.Location;
import android.location.LocationManager;
import android.os.BatteryManager;
import android.provider.CalendarContract;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

/**
 * 设备本地采集器。
 *
 * 存在的理由：App 里的数据以前靠云端定时推送，最长滞后几小时。而电量、日程、
 * 定位这些本来就是本机就能读的，天气也有免密钥的公开接口——没有理由绕一圈。
 * 这里全部本地采集，打开即当下。
 */
public class LocalProbe {

    public interface Callback {
        void onDone();
    }

    private final Context ctx;
    private volatile String cached = "";

    public LocalProbe(Context ctx) {
        this.ctx = ctx.getApplicationContext();
    }

    public String getCached() {
        return cached;
    }

    /** 在后台线程采集，完成后回调（回调在线程池线程，调用方自己 post 回主线程）。 */
    public void refresh(final Callback cb) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    cached = collect();
                } catch (Exception e) {
                    cached = "";
                }
                if (cb != null) cb.onDone();
            }
        }).start();
    }

    // ── 采集主流程 ───────────────────────────────────────────
    private String collect() throws Exception {
        JSONObject root = new JSONObject();

        JSONObject meta = new JSONObject();
        meta.put("source", "local");
        meta.put("version", "2.0");
        meta.put("generated_at", new SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.CHINA)
                .format(new Date()));
        root.put("meta", meta);

        double[] ll = location();
        JSONObject now = new JSONObject();
        JSONObject daily = new JSONObject();
        String city = "";
        if (ll != null) {
            try {
                JSONObject w = weather(ll[0], ll[1]);
                if (w != null) {
                    JSONObject wn = w.optJSONObject("now");
                    JSONObject wd = w.optJSONObject("today");
                    if (wn != null) now = wn;
                    if (wd != null) daily = wd;
                    city = w.optString("city", "");
                }
            } catch (Exception ignored) { }
        }

        JSONObject t = new JSONObject();
        t.put("city", city);
        t.put("address", "");
        t.put("battery", battery());
        t.put("now", now);
        t.put("daily", daily);
        t.put("tips", new JSONArray());
        t.put("events", events());
        t.put("headline", headline(now, daily));
        root.put("today", t);

        return root.toString();
    }

    // ── 电量 ────────────────────────────────────────────────
    private String battery() {
        try {
            BatteryManager bm = (BatteryManager) ctx.getSystemService(Context.BATTERY_SERVICE);
            if (bm == null) return "";
            int p = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY);
            return (p >= 0 && p <= 100) ? p + "%" : "";
        } catch (Exception e) {
            return "";
        }
    }

    // ── 定位 ────────────────────────────────────────────────
    private double[] location() {
        if (ctx.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) {
            return null;
        }
        try {
            LocationManager lm = (LocationManager) ctx.getSystemService(Context.LOCATION_SERVICE);
            if (lm == null) return null;
            Location best = null;
            for (String p : new String[]{LocationManager.GPS_PROVIDER,
                    LocationManager.NETWORK_PROVIDER, LocationManager.PASSIVE_PROVIDER}) {
                try {
                    Location l = lm.getLastKnownLocation(p);
                    if (l != null && (best == null || l.getTime() > best.getTime())) best = l;
                } catch (SecurityException ignored) { }
            }
            return best == null ? null : new double[]{best.getLatitude(), best.getLongitude()};
        } catch (Exception e) {
            return null;
        }
    }

    // ── 天气（open-meteo，免密钥）─────────────────────────────
    private JSONObject weather(double lat, double lon) throws Exception {
        String url = String.format(Locale.US,
                "https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f"
                        + "&current=temperature_2m,relative_humidity_2m,weather_code"
                        + "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
                        + "&timezone=Asia%%2FShanghai&forecast_days=2", lat, lon);
        String body = httpGet(url);
        if (body == null) return null;
        JSONObject j = new JSONObject(body);

        JSONObject cur = j.getJSONObject("current");
        JSONObject daily = j.getJSONObject("daily");
        JSONArray tmax = daily.getJSONArray("temperature_2m_max");
        JSONArray tmin = daily.getJSONArray("temperature_2m_min");
        JSONArray pop = daily.optJSONArray("precipitation_probability_max");

        int code = cur.optInt("weather_code", -1);
        JSONObject now = new JSONObject();
        now.put("temp", Math.round(cur.optDouble("temperature_2m", 0)) + "℃");
        now.put("text", wmo(code));
        now.put("humidity", Math.round(cur.optDouble("relative_humidity_2m", 0)) + "%");
        now.put("aqi", "");
        now.put("quality", "");

        JSONObject td = new JSONObject();
        td.put("day", wmo(code));
        td.put("high", Math.round(tmax.optDouble(0, 0)) + "℃");
        td.put("low", Math.round(tmin.optDouble(0, 0)) + "℃");
        td.put("pop", pop != null ? pop.optInt(0, 0) : 0);

        JSONObject out = new JSONObject();
        out.put("now", now);
        out.put("today", td);
        return out;
    }

    private String httpGet(String u) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(u).openConnection();
            c.setConnectTimeout(6000);
            c.setReadTimeout(6000);
            c.setRequestMethod("GET");
            if (c.getResponseCode() != 200) return null;
            InputStream in = c.getInputStream();
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0) bos.write(buf, 0, n);
            in.close();
            return bos.toString("UTF-8");
        } catch (Exception e) {
            return null;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private static String wmo(int code) {
        if (code == 0) return "晴";
        if (code == 1 || code == 2) return "多云";
        if (code == 3) return "阴";
        if (code == 45 || code == 48) return "雾";
        if (code >= 51 && code <= 57) return "毛毛雨";
        if (code >= 61 && code <= 67) return "雨";
        if (code >= 71 && code <= 77) return "雪";
        if (code >= 80 && code <= 82) return "阵雨";
        if (code == 95 || code == 96 || code == 99) return "雷雨";
        return "—";
    }

    // ── 日程 ────────────────────────────────────────────────
    private JSONArray events() {
        JSONArray arr = new JSONArray();
        if (ctx.checkSelfPermission(Manifest.permission.READ_CALENDAR)
                != PackageManager.PERMISSION_GRANTED) {
            return arr;
        }
        Cursor c = null;
        try {
            Calendar start = Calendar.getInstance(TimeZone.getDefault());
            start.set(Calendar.HOUR_OF_DAY, 0);
            start.set(Calendar.MINUTE, 0);
            start.set(Calendar.SECOND, 0);
            Calendar end = (Calendar) start.clone();
            end.add(Calendar.DAY_OF_MONTH, 1);

            String uri = "content://com.android.calendar/instances/when/"
                    + start.getTimeInMillis() + "/" + end.getTimeInMillis();
            c = ctx.getContentResolver().query(android.net.Uri.parse(uri),
                    new String[]{"title", "begin", "end"},
                    null, null, "begin ASC");
            SimpleDateFormat hm = new SimpleDateFormat("HH:mm", Locale.CHINA);
            int guard = 0;
            while (c != null && c.moveToNext() && guard++ < 12) {
                JSONObject e = new JSONObject();
                e.put("title", c.getString(0) == null ? "" : c.getString(0));
                e.put("start", hm.format(new Date(c.getLong(1))));
                e.put("end", hm.format(new Date(c.getLong(2))));
                arr.put(e);
            }
        } catch (Exception ignored) {
        } finally {
            if (c != null) c.close();
        }
        return arr;
    }

    private String headline(JSONObject now, JSONObject today) {
        try {
            StringBuilder sb = new StringBuilder();
            if (now.has("temp")) {
                sb.append("此刻 ").append(now.optString("temp")).append(" ")
                        .append(now.optString("text", ""));
                if (today.has("low")) {
                    sb.append("，今天 ").append(today.optString("low")).append("–")
                            .append(today.optString("high", ""));
                }
                int pop = today.optInt("pop", 0);
                if (pop >= 40) sb.append("，降水概率 ").append(pop).append("%，记得带伞");
                sb.append("。");
            }
            if (now.has("humidity")) {
                sb.append("湿度 ").append(now.optString("humidity")).append("。");
            }
            return sb.toString();
        } catch (Exception e) {
            return "";
        }
    }
}
