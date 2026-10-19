"""NeoPilot 预置例程库.

每个例程 = 一条时间表 + 一串原子能力步骤 + 一组验收规则。
步骤里只写 method 与参数，真正的调用由执行方（agent 或人）完成，
引擎负责推进游标、记录证据、判定成败。
"""

from __future__ import annotations

from typing import Dict, List

# 参数模板变量：$today / $tomorrow / $now / $now_plus_1h / $weekday


def _step(sid, cap, label, params=None, must=True, retry=0) -> Dict:
    return {
        "id": sid,
        "cap": cap,
        "label": label,
        "params": params or {},
        "must": must,
        "retry": retry,
    }


PRESETS: List[Dict] = [
    {
        "id": "morning-cockpit",
        "name": "晨间驾驶舱",
        "emoji": "",
        "desc": "起床后 20 分钟内跑完：今天什么天气、几点有什么会、手机还剩多少电、要不要带伞。",
        "schedule": "50 7 * * *",
        "schedule_text": "每天 07:50",
        "enabled": True,
        "tags": ["每日", "信息聚合"],
        "steps": [
            _step("weather", "weather_get_current_location_weather", "查今天天气",
                  {"type": "by_date", "startDate": "$today", "endDate": "$today"}),
            _step("calendar", "calendar_query_event", "拉今天日程",
                  {"start_time": "$today_0000", "end_time": "$today_2359"}),
            _step("battery", "settings_get_current_battery_level", "读电量"),
            _step("location", "get_current_location", "确认所在位置", must=False),
        ],
        "verify": {"min_ok": 3, "must_all_ok": True},
    },
    {
        "id": "commute-ready",
        "name": "出门前检查",
        "emoji": "",
        "desc": "出门前十分钟：逐时天气 + 到公司的路线耗时，决定几点走、骑车还是打车。",
        "schedule": "20 8 * * 1-5",
        "schedule_text": "工作日 08:20",
        "enabled": True,
        "tags": ["工作日", "出行"],
        "steps": [
            _step("hourly", "weather_get_current_location_weather", "查未来几小时天气",
                  {"type": "by_hour", "startDate": "$today", "startHour": "$hour"}),
            _step("route", "amap_route_card", "算到公司的路线",
                  {"origin": "$loc_gcj", "destination": "$home_work_gcj", "mode": "driving"}),
        ],
        "verify": {"min_ok": 1, "must_all_ok": True},
        "requires": ["home_work_gcj"],
    },
    {
        "id": "focus-block",
        "name": "专注模式",
        "emoji": "",
        "desc": "进入深度工作前一键降噪：开省电、关震动、亮度调低、起 50 分钟倒计时。",
        "schedule": "30 9 * * 1-5",
        "schedule_text": "工作日 09:30",
        "enabled": False,
        "tags": ["专注", "设备"],
        "steps": [
            _step("saver", "settings_battery_saver_switch", "开省电模式", {"openState": True}),
            _step("vibrate", "settings_vibration_switch", "关系统震动", {"openState": False}),
            _step("bright", "settings_adjust_brightness", "亮度降到 40%", {"newValue": "40"}),
            _step("timer", "alarm_clock_timer_add", "起 50 分钟计时", {"seconds": 3000, "label": "专注块"}),
        ],
        "verify": {"min_ok": 4, "must_all_ok": True},
    },
    {
        "id": "leave-work",
        "name": "下班前播报",
        "emoji": "",
        "desc": "下班前看天、看路、看明天第一件事，避免出门才发现下雨或堵死。",
        "schedule": "30 18 * * 1-5",
        "schedule_text": "工作日 18:30",
        "enabled": False,
        "tags": ["工作日", "出行"],
        "steps": [
            _step("hourly", "weather_get_current_location_weather", "查下班时段天气",
                  {"type": "by_hour", "startDate": "$today", "startHour": "$hour"}),
            _step("route", "amap_route_card", "算回家路线",
                  {"origin": "$loc_gcj", "destination": "$home_work_gcj", "mode": "driving"}),
            _step("tomorrow", "calendar_query_event", "看明天的第一件事",
                  {"start_time": "$tomorrow_0000", "end_time": "$tomorrow_2359"}),
        ],
        "verify": {"min_ok": 2, "must_all_ok": False},
        "requires": ["home_work_gcj"],
    },
    {
        "id": "evening-review",
        "name": "晚间复盘",
        "emoji": "",
        "desc": "睡前收盘：今天做成什么、明天几点起、要不要现在把闹钟定掉。",
        "schedule": "0 22 * * *",
        "schedule_text": "每天 22:00",
        "enabled": True,
        "tags": ["每日", "复盘"],
        "steps": [
            _step("today", "calendar_query_event", "回看今天日程",
                  {"start_time": "$today_0000", "end_time": "$today_2359"}),
            _step("tomorrow", "calendar_query_event", "预读明天日程",
                  {"start_time": "$tomorrow_0000", "end_time": "$tomorrow_2359"}),
            _step("weather", "weather_get_current_location_weather", "查明天天气",
                  {"type": "by_date", "startDate": "$tomorrow", "endDate": "$tomorrow"}),
            _step("battery", "settings_get_current_battery_level", "读电量判断是否该充电"),
        ],
        "verify": {"min_ok": 3, "must_all_ok": True},
    },
    {
        "id": "sleep-mode",
        "name": "睡前静音",
        "emoji": "",
        "desc": "把设备和人都切到夜间档：亮度压低、震动关掉、定好明早闹钟。",
        "schedule": "15 23 * * *",
        "schedule_text": "每天 23:15",
        "enabled": False,
        "tags": ["夜间", "设备"],
        "steps": [
            _step("bright", "settings_adjust_brightness", "亮度降到 15%", {"newValue": "15"}),
            _step("vibrate", "settings_vibration_switch", "关系统震动", {"openState": False}),
            _step("alarm", "alarm_clock_add", "定明早闹钟",
                  {"hour": 7, "minute": 30, "label": "起床", "repeatDays": 1, "vibrate": True}),
        ],
        "verify": {"min_ok": 3, "must_all_ok": True},
    },
    {
        "id": "travel-day",
        "name": "出行日包",
        "emoji": "",
        "desc": "出差或旅行当天手动触发：天气、路线、目的地周边一次备齐。",
        "schedule": "",
        "schedule_text": "手动触发",
        "enabled": True,
        "tags": ["出行", "手动"],
        "steps": [
            _step("weather", "weather_get_current_location_weather", "查当地天气",
                  {"type": "by_date", "startDate": "$today", "endDate": "$tomorrow"}),
            _step("transit", "maps_direction_transit_integrated", "备一份公交方案",
                  {"origin": "$loc_gcj", "destination": "$home_work_gcj",
                   "city": "$city", "cityd": "$city"}, must=False),
            _step("nearby", "amap_overview_card", "看看目的地周边",
                  {"keywords": "餐饮", "location": "$loc_gcj", "radius": "1500", "limit": "5"}, must=False),
        ],
        "verify": {"min_ok": 1, "must_all_ok": False},
        "requires": ["home_work_gcj"],
    },
    {
        "id": "weekly-archive",
        "name": "周度归档",
        "emoji": "",
        "desc": "把这一周拍的照片按周归进相册，顺手清一次历史运行记录。",
        "schedule": "0 20 * * 0",
        "schedule_text": "每周日 20:00",
        "enabled": False,
        "tags": ["每周", "整理"],
        "steps": [
            _step("search", "gallery_local_search", "找出本周照片",
                  {"start_time": "$week_start", "end_time": "$today_2359"}),
            # 实测：gallery_create_album 会拉起相册界面等用户选图（返回 10402），
            # 不是无头能力，所以降级为可选，跑不通不影响整条例程。
            _step("album", "gallery_create_album", "建本周相册（需在相册界面确认）",
                  {"albumName": "$week_album"}, must=False),
        ],
        "verify": {"min_ok": 1, "must_all_ok": True},
    },
]

# 单次冷启动的实况体检例程：不排表，专门用来验证引擎与设备链路是否通。
PROBE = {
    "id": "env-probe",
    "name": "环境实况体检",
    "emoji": "",
    "desc": "一次点击验证设备链路：电量、定位、天气、今日日程四项实测。",
    "schedule": "",
    "schedule_text": "手动触发",
    "enabled": True,
    "tags": ["诊断", "手动"],
    "steps": [
        _step("battery", "settings_get_current_battery_level", "读电量"),
        _step("location", "get_current_location", "取当前位置"),
        _step("weather", "weather_get_current_location_weather", "查今日天气",
              {"type": "by_date", "startDate": "$today", "endDate": "$today"}),
        _step("calendar", "calendar_query_event", "查今日日程",
              {"start_time": "$today_0000", "end_time": "$today_2359"}),
    ],
    "verify": {"min_ok": 4, "must_all_ok": True},
}


def all_presets() -> List[Dict]:
    return PRESETS + [PROBE]
